from decimal import Decimal
from unittest.mock import patch
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.models import AuditLog
from apps.campaigns.models import Campaign, Category
from apps.users.models import User
import services.audit_service as audit_service
import services.donation_service as donation_service


def make_campaign(**kwargs):
    owner = kwargs.pop('owner', None) or User.objects.create_user(
        email=f'audit-owner{User.objects.count()}@example.com', password='pass', email_verified=True,
    )
    category = kwargs.pop('category', None) or Category.objects.create(name=f'Cat {Category.objects.count()}')
    defaults = {
        'owner': owner,
        'category': category,
        'title': 'Well for Bakau',
        'slug': f'well-for-bakau-{Campaign.objects.count()}',
        'short_description': 'Clean water',
        'story': 'A well for the community.',
        'goal': Decimal('10000.00'),
        'status': Campaign.Status.ACTIVE,
    }
    defaults.update(kwargs)
    return Campaign.objects.create(**defaults)


def authed_client(client, user):
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')


class AuditServiceTest(APITestCase):
    def test_log_creates_an_entry_with_denormalized_actor_name_and_email(self):
        user = User.objects.create_user(email='actor@example.com', password='pass', first_name='Alagie', last_name='Admin')
        campaign = make_campaign()
        audit_service.log(user, AuditLog.Action.CAMPAIGN_CREATED, campaign, 'Created campaign "X"')
        entry = AuditLog.objects.get(action=AuditLog.Action.CAMPAIGN_CREATED)
        self.assertEqual(entry.actor, user)
        self.assertEqual(entry.actor_name, 'Alagie Admin')
        self.assertEqual(entry.actor_email, 'actor@example.com')
        self.assertEqual(entry.target_type, 'Campaign')
        self.assertEqual(entry.target_id, str(campaign.pk))

    def test_verb_reflects_the_action(self):
        campaign = make_campaign()
        audit_service.log(None, AuditLog.Action.CAMPAIGN_DELETED, None, 'x')
        entry = AuditLog.objects.get(action=AuditLog.Action.CAMPAIGN_DELETED)
        self.assertEqual(entry.verb, 'deleted')

    def test_get_audit_actors_only_lists_users_with_entries(self):
        active_user = User.objects.create_user(email='hasentry@example.com', password='pass')
        User.objects.create_user(email='noentry@example.com', password='pass')
        audit_service.log(active_user, AuditLog.Action.CAMPAIGN_CREATED, None, 'x')
        actors = list(audit_service.get_audit_actors())
        self.assertIn(active_user, actors)
        self.assertEqual(len(actors), 1)

    def test_actor_email_override_is_used_instead_of_a_live_read(self):
        # Covers self-service account deletion, which anonymizes the
        # actor's email as part of the very action being logged.
        user = User.objects.create_user(email='real@example.com', password='pass')
        audit_service.log(user, AuditLog.Action.USER_ACCOUNT_DELETED, None, 'Deleted account', actor_email='real@example.com')
        user.email = 'anon-1234@deleted.local'
        user.save(update_fields=['email'])
        entry = AuditLog.objects.get(action=AuditLog.Action.USER_ACCOUNT_DELETED)
        self.assertEqual(entry.actor_email, 'real@example.com')

    def test_none_actor_is_allowed_for_system_triggered_actions(self):
        campaign = make_campaign()
        audit_service.log(None, AuditLog.Action.CAMPAIGN_PUBLISHED, campaign, 'System action')
        entry = AuditLog.objects.get(action=AuditLog.Action.CAMPAIGN_PUBLISHED)
        self.assertIsNone(entry.actor)
        self.assertEqual(entry.actor_email, '')

    def test_log_never_raises_even_if_something_goes_wrong(self):
        # A broken/garbage action value must not blow up the real request
        # it's supposed to be describing alongside.
        audit_service.log('not-a-user-object', 'not.a.real.action', None, 'whatever')
        # No exception -- that's the assertion.


class CampaignAuditTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='owner@example.com', password='pass', email_verified=True)
        authed_client(self.client, self.user)

    def test_creating_a_campaign_is_audited(self):
        response = self.client.post('/api/v1/campaigns/create/', {
            'title': 'Flood Relief', 'category_id': Category.objects.create(name='Disaster').id,
            'short_description': 'Help', 'story': 'Story', 'goal': '5000.00',
            'beneficiary': 'Me', 'beneficiary_relationship': 'Self', 'region': 'banjul',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        entry = AuditLog.objects.filter(action=AuditLog.Action.CAMPAIGN_CREATED).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.actor, self.user)
        self.assertIn('Flood Relief', entry.description)

    def test_deleting_a_draft_campaign_is_audited_with_its_title_preserved(self):
        campaign = make_campaign(owner=self.user, status=Campaign.Status.DRAFT, title='Old Draft')
        response = self.client.delete(f'/api/v1/campaigns/my/{campaign.slug}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        entry = AuditLog.objects.filter(action=AuditLog.Action.CAMPAIGN_DELETED).first()
        self.assertIsNotNone(entry)
        self.assertIn('Old Draft', entry.description)

    def test_toggling_pause_logs_published_or_unpublished(self):
        campaign = make_campaign(owner=self.user, status=Campaign.Status.ACTIVE)
        response = self.client.post(f'/api/v1/campaigns/my/{campaign.slug}/pause/')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        entry = AuditLog.objects.filter(action=AuditLog.Action.CAMPAIGN_UNPUBLISHED).first()
        self.assertIsNotNone(entry)

    def test_admin_approving_a_campaign_logs_published(self):
        admin = User.objects.create_user(email='admin@example.com', password='pass', role=User.Role.ADMIN)
        authed_client(self.client, admin)
        campaign = make_campaign(status=Campaign.Status.PENDING)
        response = self.client.post(f'/api/v1/campaigns/admin/{campaign.pk}/action/approve/')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        entry = AuditLog.objects.filter(action=AuditLog.Action.CAMPAIGN_PUBLISHED).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.actor, admin)


class UserAuditTest(APITestCase):
    def test_role_change_is_audited_with_old_and_new_role(self):
        admin = User.objects.create_user(email='admin2@example.com', password='pass', role=User.Role.ADMIN)
        target = User.objects.create_user(email='target@example.com', password='pass')
        authed_client(self.client, admin)
        response = self.client.post(f'/api/v1/users/admin/staff/{target.pk}/role/', {'role': 'moderator'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        entry = AuditLog.objects.get(action=AuditLog.Action.USER_ROLE_CHANGED)
        self.assertEqual(entry.metadata['old_role'], 'user')
        self.assertEqual(entry.metadata['new_role'], 'moderator')

    def test_self_service_account_deletion_is_audited_with_the_pre_anonymization_email(self):
        user = User.objects.create_user(email='deleteme@example.com', password='pass', email_verified=True)
        authed_client(self.client, user)
        response = self.client.delete('/api/v1/users/me/', {'password': 'pass'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        entry = AuditLog.objects.get(action=AuditLog.Action.USER_ACCOUNT_DELETED)
        self.assertEqual(entry.actor_email, 'deleteme@example.com')
        self.assertIn('deleteme@example.com', entry.description)


class DonationAuditTest(APITestCase):
    def test_donation_creation_is_audited_even_when_the_gateway_call_fails(self):
        campaign = make_campaign()
        with patch('services.modempay_service.create_payment_intent', return_value=None):
            response = self.client.post('/api/v1/donations/', {
                'campaign_id': str(campaign.id), 'amount': '100.00', 'provider': 'wave', 'phone': '+2207000000',
            }, format='json')
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        entry = AuditLog.objects.filter(action=AuditLog.Action.DONATION_CREATED).first()
        self.assertIsNotNone(entry)

    def test_a_failed_validation_request_is_never_audited(self):
        AuditLog.objects.all().delete()
        response = self.client.post('/api/v1/donations/', {'amount': '100.00'}, format='json')  # missing campaign_id
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.DONATION_CREATED).exists())

    def test_successful_login_is_audited_with_the_real_actor_name(self):
        user = User.objects.create_user(
            email='loginuser@example.com', password='pass', email_verified=True,
            first_name='Login', last_name='User',
        )
        self.client.post('/api/v1/auth/login/', {'email': 'loginuser@example.com', 'password': 'pass'}, format='json')
        entry = AuditLog.objects.get(action=AuditLog.Action.USER_LOGGED_IN)
        self.assertEqual(entry.actor, user)
        self.assertEqual(entry.actor_name, 'Login User')
        self.assertNotEqual(entry.actor_name, '')

    def test_a_failed_login_attempt_is_not_audited(self):
        User.objects.create_user(email='wrongpass@example.com', password='pass', email_verified=True)
        response = self.client.post('/api/v1/auth/login/', {'email': 'wrongpass@example.com', 'password': 'nope'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.USER_LOGGED_IN).exists())

    def test_guest_donation_is_attributed_to_their_given_name_not_system(self):
        campaign = make_campaign()
        with patch(
            'services.modempay_service.create_payment_intent',
            return_value={'status': True, 'data': {'payment_link': 'https://pay.example/x', 'intent_secret': 'sec'}},
        ):
            response = self.client.post('/api/v1/donations/', {
                'campaign_id': str(campaign.id), 'amount': '100.00', 'provider': 'wave',
                'phone': '+2207000000', 'donor_name': 'Musa Jallow',
            }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        entry = AuditLog.objects.get(action=AuditLog.Action.DONATION_CREATED)
        self.assertIsNone(entry.actor)
        self.assertEqual(entry.actor_name, 'Musa Jallow')
        self.assertNotEqual(entry.actor_name, 'System')
        self.assertIn('Musa Jallow', entry.description)

    def test_confirming_a_donation_logs_a_status_change_with_no_actor(self):
        campaign = make_campaign()
        from apps.donations.models import Donation
        donation = Donation.objects.create(
            campaign=campaign, amount=Decimal('50.00'), currency='GMD', provider='wave', phone='+2207000000',
            payment_reference='SD-AUDIT1', gateway='modempay', status=Donation.Status.PENDING,
        )
        donation_service.confirm_donation_by_reference('SD-AUDIT1')
        entry = AuditLog.objects.get(action=AuditLog.Action.DONATION_STATUS_CHANGED)
        self.assertIsNone(entry.actor)
        self.assertIn('paid', entry.description)


class ExpandedAuditCoverageTest(APITestCase):
    """The activities explicitly asked for beyond the original curated
    list: login/registration/password-reset/profile-updates, moderation
    (reports, verification), and staff management."""

    def test_registration_is_audited(self):
        response = self.client.post('/api/v1/auth/register/', {
            'email': 'newperson@example.com', 'password': 'StrongPass@1',
            'password_confirm': 'StrongPass@1', 'terms_accepted': True,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        entry = AuditLog.objects.get(action=AuditLog.Action.USER_REGISTERED)
        # Registration collects no name yet (filled in later during
        # onboarding) -- full_name falls back to the email itself.
        self.assertEqual(entry.actor_name, 'newperson@example.com')

    def test_password_reset_completion_is_audited_via_signal(self):
        from django_rest_passwordreset.signals import post_password_reset
        user = User.objects.create_user(email='resetme@example.com', password='oldpass', first_name='Reset', last_name='Me')
        post_password_reset.send(sender=self.__class__, user=user)
        entry = AuditLog.objects.get(action=AuditLog.Action.USER_PASSWORD_RESET)
        self.assertEqual(entry.actor, user)
        self.assertIn('Reset Me', entry.description)

    def test_profile_update_is_audited(self):
        user = User.objects.create_user(email='profileuser@example.com', password='pass', email_verified=True)
        authed_client(self.client, user)
        response = self.client.patch('/api/v1/users/me/', {'bio': 'New bio'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        entry = AuditLog.objects.get(action=AuditLog.Action.USER_PROFILE_UPDATED)
        self.assertEqual(entry.actor, user)

    def test_staff_creation_is_audited(self):
        admin = User.objects.create_user(email='staffadmin@example.com', password='pass', role=User.Role.ADMIN)
        authed_client(self.client, admin)
        response = self.client.post('/api/v1/users/admin/create/', {
            'email': 'newstaff@example.com', 'role': User.Role.MODERATOR, 'first_name': 'New', 'last_name': 'Staff',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        entry = AuditLog.objects.get(action=AuditLog.Action.STAFF_CREATED)
        self.assertEqual(entry.actor, admin)
        self.assertIn('New Staff', entry.description)

    def test_report_status_change_is_audited(self):
        from apps.campaigns.models import CampaignReport
        admin = User.objects.create_user(email='reportadmin@example.com', password='pass', role=User.Role.ADMIN)
        campaign = make_campaign()
        report = CampaignReport.objects.create(
            campaign=campaign, reason=CampaignReport.Reason.SPAM, description='spammy',
        )
        authed_client(self.client, admin)
        response = self.client.patch(f'/api/v1/campaigns/admin/reports/{report.pk}/update/', {
            'status': 'resolved',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        entry = AuditLog.objects.get(action=AuditLog.Action.REPORT_STATUS_CHANGED)
        self.assertEqual(entry.actor, admin)

    def test_identity_verification_approval_is_audited(self):
        from apps.users.models import IdentityVerification
        from django.core.files.uploadedfile import SimpleUploadedFile
        admin = User.objects.create_user(email='verifyadmin@example.com', password='pass', role=User.Role.ADMIN)
        target = User.objects.create_user(email='verifyme@example.com', password='pass', first_name='Verify', last_name='Me')
        verification = IdentityVerification.objects.create(
            user=target, id_type=IdentityVerification.IdType.NATIONAL_ID, id_number='123',
            id_photo_front=SimpleUploadedFile('id.jpg', b'fake', content_type='image/jpeg'),
        )
        authed_client(self.client, admin)
        response = self.client.post(f'/api/v1/users/admin/verifications/{verification.pk}/approve/')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        entry = AuditLog.objects.get(action=AuditLog.Action.VERIFICATION_APPROVED)
        self.assertEqual(entry.actor, admin)
        self.assertIn('Verify Me', entry.description)


class AdminAuditLogListViewTest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(email='listadmin@example.com', password='pass', role=User.Role.ADMIN)
        self.regular_user = User.objects.create_user(email='listuser@example.com', password='pass')
        campaign = make_campaign()
        audit_service.log(self.admin, AuditLog.Action.CAMPAIGN_PUBLISHED, campaign, 'Published campaign "X"')
        audit_service.log(None, AuditLog.Action.DONATION_STATUS_CHANGED, None, 'Donation marked paid')

    def test_admin_can_list_entries(self):
        authed_client(self.client, self.admin)
        response = self.client.get('/api/v1/audit/admin/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)

    def test_non_admin_is_forbidden(self):
        authed_client(self.client, self.regular_user)
        response = self.client.get('/api/v1/audit/admin/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_filter_by_action(self):
        authed_client(self.client, self.admin)
        response = self.client.get('/api/v1/audit/admin/', {'action': AuditLog.Action.CAMPAIGN_PUBLISHED})
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['action'], AuditLog.Action.CAMPAIGN_PUBLISHED)

    def test_action_choices_endpoint(self):
        authed_client(self.client, self.admin)
        response = self.client.get('/api/v1/audit/admin/actions/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        values = [a['value'] for a in response.data['data']['actions']]
        self.assertIn(AuditLog.Action.DONATION_CREATED, values)

    def test_actors_endpoint_lists_only_users_with_entries(self):
        authed_client(self.client, self.admin)
        response = self.client.get('/api/v1/audit/admin/actors/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        actor_ids = [a['id'] for a in response.data['data']['actors']]
        self.assertIn(str(self.admin.id), actor_ids)
        self.assertNotIn(str(self.regular_user.id), actor_ids)

    def test_entries_include_actor_name_and_verb(self):
        authed_client(self.client, self.admin)
        response = self.client.get('/api/v1/audit/admin/', {'action': AuditLog.Action.CAMPAIGN_PUBLISHED})
        entry = response.data['results'][0]
        self.assertEqual(entry['actor_name'], self.admin.full_name)
        self.assertEqual(entry['verb'], 'published')
