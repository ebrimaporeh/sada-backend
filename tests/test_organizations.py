from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import User, Organization
from apps.campaigns.models import Campaign, Category
from apps.organizations.models import OrganizationType, OrganizationRole, OrganizationMembership, OrganizationInvitation
from apps.organizations.permissions import OrganizationPermission, ALL_ORGANIZATION_PERMISSIONS
import services.organization_service as organization_service
import services.campaign_service as campaign_service
import services.payment_service as payment_service


def make_org_type(**kwargs):
    defaults = {'slug': f'org-type-{OrganizationType.objects.count()}', 'name': 'Community-Based Organization', 'is_visible': True}
    defaults.update(kwargs)
    return OrganizationType.objects.create(**defaults)


def make_org_and_owner(**kwargs):
    """Returns (user, organization) -- user is the org's Owner-role member,
    created via organization_service.create_organization() itself so these
    tests exercise the real Owner/Member-role bootstrapping, not a hand-rolled
    shortcut."""
    org_type = kwargs.pop('org_type', None) or make_org_type()
    user = kwargs.pop('user', None) or User.objects.create_user(
        email=f'owner{User.objects.count()}@example.com', password='pass',
    )
    org = organization_service.create_organization(
        user,
        organization_name=kwargs.pop('organization_name', 'Test Org'),
        organization_type_slug=org_type.slug,
    )
    return user, org


def make_member(org, role_name=None, permissions=None):
    """Creates a new user and adds them to `org` under a fresh role (default
    permissions=[] unless given, or role_name to reuse/create a named role)."""
    user = User.objects.create_user(email=f'member{User.objects.count()}@example.com', password='pass')
    if role_name:
        role, _ = OrganizationRole.objects.get_or_create(
            organization=org, name=role_name, defaults={'permissions': permissions or []},
        )
    else:
        role = OrganizationRole.objects.create(
            organization=org, name=f'Role {OrganizationRole.objects.count()}', permissions=permissions or [],
        )
    OrganizationMembership.objects.create(user=user, organization=org, role=role)
    return user, role


def make_category(**kwargs):
    defaults = {'name': f'Category {Category.objects.count()}'}
    defaults.update(kwargs)
    return Category.objects.create(**defaults)


def make_campaign(**kwargs):
    owner = kwargs.pop('owner', None) or User.objects.create_user(
        email=f'campowner{User.objects.count()}@example.com', password='pass',
    )
    category = kwargs.pop('category', None) or make_category()
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


class CreateOrganizationTest(APITestCase):
    def test_creates_org_with_owner_and_member_roles(self):
        org_type = make_org_type()
        user = User.objects.create_user(email='founder@example.com', password='pass')

        org = organization_service.create_organization(
            user, organization_name='Gambia Youth Trust', organization_type_slug=org_type.slug,
        )

        self.assertEqual(org.created_by, user)
        owner_role = OrganizationRole.objects.get(organization=org, name='Owner')
        member_role = OrganizationRole.objects.get(organization=org, name='Member')
        self.assertEqual(set(owner_role.permissions), set(ALL_ORGANIZATION_PERMISSIONS))
        self.assertEqual(member_role.permissions, [OrganizationPermission.CREATE_CAMPAIGN])
        membership = OrganizationMembership.objects.get(user=user, organization=org)
        self.assertEqual(membership.role, owner_role)
        # The creator is the org's first contact person automatically --
        # there's always someone real to reach.
        self.assertTrue(membership.is_contact_person)

    def test_rejects_a_non_visible_organization_type(self):
        hidden_type = make_org_type(slug='hidden-type', name='Hidden Type', is_visible=False)
        user = User.objects.create_user(email='founder2@example.com', password='pass')
        with self.assertRaises(ValidationError):
            organization_service.create_organization(
                user, organization_name='Acme Ltd', organization_type_slug=hidden_type.slug,
            )

    def test_create_endpoint_round_trips_correctly(self):
        # Regression test: OrganizationCreateSerializer's field must match
        # create_organization's organization_type_slug kwarg exactly, since
        # the view splats **serializer.validated_data straight into it.
        org_type = make_org_type()
        user = User.objects.create_user(email='apifounder@example.com', password='pass')
        self.client.force_authenticate(user=user)

        response = self.client.post(reverse('organization-create'), {
            'organization_name': 'API Org', 'organization_type_slug': org_type.slug,
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['data']['organization']['organization_name'], 'API Org')
        membership = OrganizationMembership.objects.get(user=user, organization__organization_name='API Org')
        self.assertTrue(membership.is_contact_person)


class RoleCrudTest(APITestCase):
    def setUp(self):
        self.owner, self.org = make_org_and_owner()

    def test_manage_members_required_to_create_role(self):
        outsider = User.objects.create_user(email='outsider@example.com', password='pass')
        with self.assertRaises(PermissionDenied):
            organization_service.create_role(self.org, outsider, name='Treasurer', permissions=[OrganizationPermission.WITHDRAW_FUNDS])

    def test_owner_can_create_and_use_a_custom_role(self):
        role = organization_service.create_role(
            self.org, self.owner, name='Treasurer', permissions=[OrganizationPermission.WITHDRAW_FUNDS],
        )
        self.assertEqual(role.permissions, [OrganizationPermission.WITHDRAW_FUNDS])

    def test_cannot_create_role_with_reserved_name(self):
        with self.assertRaises(ValidationError):
            organization_service.create_role(self.org, self.owner, name='Owner', permissions=[])

    def test_cannot_create_role_with_unknown_permission(self):
        with self.assertRaises(ValidationError):
            organization_service.create_role(self.org, self.owner, name='Ghost', permissions=['delete_everything'])

    def test_owner_role_cannot_be_edited_or_deleted(self):
        owner_role = OrganizationRole.objects.get(organization=self.org, name='Owner')
        with self.assertRaises(ValidationError):
            organization_service.update_role(owner_role, self.owner, name='Super Owner')
        with self.assertRaises(ValidationError):
            organization_service.delete_role(owner_role, self.owner)

    def test_role_still_assigned_to_a_member_cannot_be_deleted(self):
        role = organization_service.create_role(self.org, self.owner, name='Volunteer', permissions=[])
        make_member(self.org, role_name='Volunteer')
        with self.assertRaises(ValidationError):
            organization_service.delete_role(role, self.owner)

    def test_unused_custom_role_can_be_deleted(self):
        role = organization_service.create_role(self.org, self.owner, name='Unused', permissions=[])
        organization_service.delete_role(role, self.owner)
        self.assertFalse(OrganizationRole.objects.filter(pk=role.pk).exists())


class MembershipTest(APITestCase):
    def setUp(self):
        self.owner, self.org = make_org_and_owner()

    def test_member_can_remove_themselves(self):
        member, _ = make_member(self.org)
        organization_service.remove_member(self.org, member, member)
        self.assertFalse(OrganizationMembership.objects.filter(user=member, organization=self.org).exists())

    def test_removing_someone_else_requires_manage_members(self):
        member, _ = make_member(self.org)
        outsider, _ = make_member(self.org)
        with self.assertRaises(PermissionDenied):
            organization_service.remove_member(self.org, outsider, member)

    def test_manager_can_remove_another_member(self):
        member, _ = make_member(self.org)
        organization_service.remove_member(self.org, self.owner, member)
        self.assertFalse(OrganizationMembership.objects.filter(user=member, organization=self.org).exists())

    def test_sole_owner_cannot_leave_a_multi_member_org(self):
        make_member(self.org)
        with self.assertRaises(ValidationError):
            organization_service.remove_member(self.org, self.owner, self.owner)

    def test_sole_owner_of_a_single_member_org_can_leave(self):
        # No invariant violated -- the org just ends up with zero members.
        organization_service.remove_member(self.org, self.owner, self.owner)
        self.assertFalse(OrganizationMembership.objects.filter(organization=self.org).exists())

    def test_change_member_role_requires_manage_members(self):
        member, _ = make_member(self.org)
        outsider, _ = make_member(self.org)
        new_role = organization_service.create_role(self.org, self.owner, name='Editor', permissions=[OrganizationPermission.EDIT_CAMPAIGN])
        with self.assertRaises(PermissionDenied):
            organization_service.change_member_role(self.org, outsider, member, new_role)

    def test_change_member_role_updates_it(self):
        member, _ = make_member(self.org)
        new_role = organization_service.create_role(self.org, self.owner, name='Editor', permissions=[OrganizationPermission.EDIT_CAMPAIGN])
        updated = organization_service.change_member_role(self.org, self.owner, member, new_role)
        self.assertEqual(updated.role, new_role)

    def test_cannot_change_role_into_or_out_of_owner_via_change_member_role(self):
        member, _ = make_member(self.org)
        owner_role = OrganizationRole.objects.get(organization=self.org, name='Owner')
        with self.assertRaises(ValidationError):
            organization_service.change_member_role(self.org, self.owner, member, owner_role)
        with self.assertRaises(ValidationError):
            organization_service.change_member_role(self.org, self.owner, self.owner, owner_role)


class ContactPersonTest(APITestCase):
    """Replaces Organization.contact_person_name -- contact persons are
    real members flagged via OrganizationMembership.is_contact_person, not
    a fixed name field."""

    def setUp(self):
        self.owner, self.org = make_org_and_owner()

    def test_creator_is_flagged_as_contact_person_automatically(self):
        membership = organization_service.get_membership(self.owner, self.org)
        self.assertTrue(membership.is_contact_person)

    def test_manager_can_flag_another_member_as_a_second_contact_person(self):
        member, _ = make_member(self.org, permissions=[])
        updated = organization_service.set_contact_person(self.org, self.owner, member, True)
        self.assertTrue(updated.is_contact_person)
        contacts = list(organization_service.get_contact_persons(self.org))
        self.assertEqual({c.user_id for c in contacts}, {self.owner.id, member.id})

    def test_can_unflag_a_contact_person(self):
        member, _ = make_member(self.org, permissions=[])
        organization_service.set_contact_person(self.org, self.owner, member, True)
        organization_service.set_contact_person(self.org, self.owner, member, False)
        contacts = list(organization_service.get_contact_persons(self.org))
        self.assertEqual({c.user_id for c in contacts}, {self.owner.id})

    def test_requires_manage_members_permission(self):
        member, _ = make_member(self.org, permissions=[])
        outsider, _ = make_member(self.org, permissions=[])
        with self.assertRaises(PermissionDenied):
            organization_service.set_contact_person(self.org, outsider, member, True)

    def test_target_must_be_a_member(self):
        outsider = User.objects.create_user(email='not-a-member@example.com', password='pass')
        with self.assertRaises(ValidationError):
            organization_service.set_contact_person(self.org, self.owner, outsider, True)

    def test_organization_serializer_exposes_contact_persons_with_real_user_details(self):
        from apps.organizations.serializers import OrganizationSerializer
        data = OrganizationSerializer(self.org, context={'request': None}).data
        self.assertEqual(len(data['contact_persons']), 1)
        self.assertEqual(data['contact_persons'][0]['email'], self.owner.email)
        self.assertEqual(data['contact_persons'][0]['name'], self.owner.full_name)

    def test_member_patch_endpoint_sets_contact_person_flag(self):
        member, _ = make_member(self.org, permissions=[])
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            reverse('organization-member-detail', args=[self.org.id, member.id]),
            {'is_contact_person': True}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data['data']['member']['is_contact_person'])

    def test_member_patch_endpoint_can_change_role_and_contact_person_together(self):
        member, _ = make_member(self.org, permissions=[])
        new_role = organization_service.create_role(self.org, self.owner, name='Treasurer', permissions=[])
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            reverse('organization-member-detail', args=[self.org.id, member.id]),
            {'role_id': str(new_role.id), 'is_contact_person': True}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['data']['member']['role_id'], str(new_role.id))
        self.assertTrue(response.data['data']['member']['is_contact_person'])


class TransferOwnershipTest(APITestCase):
    def setUp(self):
        self.owner, self.org = make_org_and_owner()

    def test_transfers_ownership_and_demotes_previous_owner_to_member(self):
        new_owner, _ = make_member(self.org)
        organization_service.transfer_ownership(self.org, self.owner, new_owner)

        new_membership = organization_service.get_membership(new_owner, self.org)
        old_membership = organization_service.get_membership(self.owner, self.org)
        self.assertEqual(new_membership.role.name, 'Owner')
        self.assertEqual(old_membership.role.name, 'Member')

    def test_only_the_current_owner_can_initiate_a_transfer(self):
        new_owner, _ = make_member(self.org)
        bystander, _ = make_member(self.org)
        with self.assertRaises(PermissionDenied):
            organization_service.transfer_ownership(self.org, bystander, new_owner)

    def test_target_must_already_be_a_member(self):
        outsider = User.objects.create_user(email='notamember@example.com', password='pass')
        with self.assertRaises(ValidationError):
            organization_service.transfer_ownership(self.org, self.owner, outsider)

    def test_exactly_one_owner_after_transfer(self):
        new_owner, _ = make_member(self.org)
        organization_service.transfer_ownership(self.org, self.owner, new_owner)
        owner_count = OrganizationMembership.objects.filter(organization=self.org, role__name='Owner').count()
        self.assertEqual(owner_count, 1)


class InvitationTest(APITestCase):
    def setUp(self):
        self.owner, self.org = make_org_and_owner()
        self.member_role = OrganizationRole.objects.get(organization=self.org, name='Member')

    @patch('emails.tasks.send_organization_invitation_email_task.delay')
    def test_invite_requires_manage_members(self, mock_delay):
        outsider, _ = make_member(self.org)
        with self.assertRaises(PermissionDenied):
            organization_service.invite_member(self.org, outsider, 'new@example.com', self.member_role)
        mock_delay.assert_not_called()

    @patch('emails.tasks.send_organization_invitation_email_task.delay')
    def test_owner_can_invite_and_email_task_is_queued(self, mock_delay):
        invitation = organization_service.invite_member(self.org, self.owner, 'invitee@example.com', self.member_role)
        self.assertEqual(invitation.status, OrganizationInvitation.Status.PENDING)
        mock_delay.assert_called_once()

    @patch('emails.tasks.send_organization_invitation_email_task.delay')
    def test_cannot_invite_to_the_owner_role(self, mock_delay):
        owner_role = OrganizationRole.objects.get(organization=self.org, name='Owner')
        with self.assertRaises(ValidationError):
            organization_service.invite_member(self.org, self.owner, 'wannabeowner@example.com', owner_role)

    @patch('emails.tasks.send_organization_invitation_email_task.delay')
    def test_cannot_invite_an_existing_member(self, mock_delay):
        existing_member, _ = make_member(self.org)
        with self.assertRaises(ValidationError):
            organization_service.invite_member(self.org, self.owner, existing_member.email, self.member_role)

    @patch('emails.tasks.send_organization_invitation_email_task.delay')
    def test_cannot_double_invite_the_same_pending_email(self, mock_delay):
        organization_service.invite_member(self.org, self.owner, 'dup@example.com', self.member_role)
        with self.assertRaises(ValidationError):
            organization_service.invite_member(self.org, self.owner, 'dup@example.com', self.member_role)

    @patch('emails.tasks.send_organization_invitation_email_task.delay')
    def test_accept_invitation_creates_membership_for_matching_email(self, mock_delay):
        invitation = organization_service.invite_member(self.org, self.owner, 'joiner@example.com', self.member_role)
        url = organization_service.generate_invitation_url(invitation)
        token = url.split('token=')[1]

        joiner = User.objects.create_user(email='joiner@example.com', password='pass')
        membership = organization_service.accept_invitation(token, joiner)

        self.assertEqual(membership.organization, self.org)
        self.assertEqual(membership.role, self.member_role)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, OrganizationInvitation.Status.ACCEPTED)

    @patch('emails.tasks.send_organization_invitation_email_task.delay')
    def test_accept_invitation_rejects_mismatched_email(self, mock_delay):
        invitation = organization_service.invite_member(self.org, self.owner, 'joiner2@example.com', self.member_role)
        url = organization_service.generate_invitation_url(invitation)
        token = url.split('token=')[1]

        wrong_person = User.objects.create_user(email='someoneelse@example.com', password='pass')
        with self.assertRaises(ValidationError):
            organization_service.accept_invitation(token, wrong_person)

    @patch('emails.tasks.send_organization_invitation_email_task.delay')
    def test_reject_invitation_leaves_no_membership(self, mock_delay):
        invitation = organization_service.invite_member(self.org, self.owner, 'decliner@example.com', self.member_role)
        url = organization_service.generate_invitation_url(invitation)
        token = url.split('token=')[1]

        decliner = User.objects.create_user(email='decliner@example.com', password='pass')
        organization_service.reject_invitation(token, decliner)

        invitation.refresh_from_db()
        self.assertEqual(invitation.status, OrganizationInvitation.Status.REJECTED)
        self.assertFalse(OrganizationMembership.objects.filter(user=decliner, organization=self.org).exists())

    def test_invitation_link_expired_is_rejected(self):
        invitation = OrganizationInvitation.objects.create(
            organization=self.org, email='late@example.com', invited_by=self.owner, role=self.member_role,
        )
        from django.core import signing
        with patch.object(signing, 'loads', side_effect=signing.SignatureExpired):
            with self.assertRaises(ValidationError):
                organization_service.preview_invitation('irrelevant-token')

    @patch('emails.tasks.send_organization_invitation_email_task.delay')
    def test_my_invitations_list_exposes_a_usable_token(self, mock_delay):
        # The "my invitations" dashboard list has no other way to link to
        # the accept/reject page -- the invitation model itself stores no
        # token, only a signed one generated on demand (see
        # organization_service.generate_invitation_token).
        organization_service.invite_member(self.org, self.owner, 'listed@example.com', self.member_role)
        invitee = User.objects.create_user(email='listed@example.com', password='pass')
        self.client.force_authenticate(user=invitee)

        response = self.client.get(reverse('organization-invitation-mine'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        token = response.data['data']['invitations'][0]['token']
        self.assertIsNotNone(token)
        membership = organization_service.accept_invitation(token, invitee)
        self.assertEqual(membership.organization, self.org)

    @patch('emails.tasks.send_organization_invitation_email_task.delay')
    def test_accept_invitation_via_api(self, mock_delay):
        invitation = organization_service.invite_member(self.org, self.owner, 'apijoiner@example.com', self.member_role)
        url = organization_service.generate_invitation_url(invitation)
        token = url.split('token=')[1]
        joiner = User.objects.create_user(email='apijoiner@example.com', password='pass')
        self.client.force_authenticate(user=joiner)

        response = self.client.post(reverse('organization-invitation-accept'), {'token': token})

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(OrganizationMembership.objects.filter(user=joiner, organization=self.org).exists())


class MyOrganizationsAndDetailViewTest(APITestCase):
    def setUp(self):
        self.owner, self.org = make_org_and_owner()

    def test_my_organizations_lists_orgs_i_belong_to(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(reverse('organization-mine'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [o['organization_name'] for o in response.data['data']['organizations']]
        self.assertIn(self.org.organization_name, names)

    def test_non_member_cannot_view_organization_detail(self):
        outsider = User.objects.create_user(email='detail-outsider@example.com', password='pass')
        self.client.force_authenticate(user=outsider)
        response = self.client.get(reverse('organization-detail', args=[self.org.id]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_member_can_view_organization_detail(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(reverse('organization-detail', args=[self.org.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['organization']['organization_name'], self.org.organization_name)


class CampaignOrganizationPermissionTest(APITestCase):
    """create_campaign/get_owner_campaign(s) integration -- individual
    campaigns behave exactly as before the org-membership redesign; org
    campaigns are gated on membership + the specific permission."""

    def setUp(self):
        self.owner, self.org = make_org_and_owner()
        self.category = make_category()

    def test_individual_campaign_still_only_owned_by_its_creator(self):
        creator = User.objects.create_user(email='soloist@example.com', password='pass')
        campaign = make_campaign(owner=creator, organization=None)
        stranger = User.objects.create_user(email='stranger@example.com', password='pass')

        fetched = campaign_service.get_owner_campaign(creator, campaign.slug)
        self.assertEqual(fetched, campaign)
        with self.assertRaises(Exception):
            campaign_service.get_owner_campaign(stranger, campaign.slug)

    def test_org_member_without_permission_gets_permission_denied_not_404(self):
        campaign = make_campaign(owner=self.owner, organization=self.org)
        powerless_member, _ = make_member(self.org, permissions=[])

        with self.assertRaises(PermissionDenied):
            campaign_service.get_owner_campaign(powerless_member, campaign.slug, required_permission=OrganizationPermission.EDIT_CAMPAIGN)

    def test_non_member_gets_404_not_permission_denied(self):
        from django.http import Http404
        campaign = make_campaign(owner=self.owner, organization=self.org)
        outsider = User.objects.create_user(email='campaign-outsider@example.com', password='pass')

        with self.assertRaises(Http404):
            campaign_service.get_owner_campaign(outsider, campaign.slug)

    def test_member_with_permission_can_act(self):
        campaign = make_campaign(owner=self.owner, organization=self.org)
        editor, _ = make_member(self.org, permissions=[OrganizationPermission.EDIT_CAMPAIGN])
        fetched = campaign_service.get_owner_campaign(editor, campaign.slug, required_permission=OrganizationPermission.EDIT_CAMPAIGN)
        self.assertEqual(fetched, campaign)

    def test_get_owner_campaigns_includes_org_campaigns_for_any_member(self):
        org_campaign = make_campaign(owner=self.owner, organization=self.org)
        member, _ = make_member(self.org, permissions=[])
        results = list(campaign_service.get_owner_campaigns(member))
        self.assertIn(org_campaign, results)

    def test_create_campaign_endpoint_requires_create_campaign_permission(self):
        powerless_member, _ = make_member(self.org, permissions=[])
        self.client.force_authenticate(user=powerless_member)

        response = self.client.post(reverse('campaign-create'), {
            'organization_id': str(self.org.id), 'category_id': str(self.category.id),
            'title': 'Blocked Campaign', 'short_description': 'desc', 'story': 'story', 'goal': '1000.00',
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_campaign_endpoint_succeeds_for_permitted_member(self):
        creator, _ = make_member(self.org, permissions=[OrganizationPermission.CREATE_CAMPAIGN])
        self.client.force_authenticate(user=creator)

        response = self.client.post(reverse('campaign-create'), {
            'organization_id': str(self.org.id), 'category_id': str(self.category.id),
            'title': 'Org Campaign', 'short_description': 'desc', 'story': 'story', 'goal': '1000.00',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        campaign = Campaign.objects.get(title='Org Campaign')
        self.assertEqual(campaign.organization, self.org)

    def test_my_campaign_list_and_detail_expose_organization_id_for_org_campaigns(self):
        # The frontend has no other way to tell an org-owned campaign apart
        # from an individual one -- organization_id on CampaignCreateSerializer
        # is write-only, so list/detail need their own read-only exposure.
        org_campaign = make_campaign(owner=self.owner, organization=self.org)
        solo_campaign = make_campaign(owner=self.owner, organization=None)
        self.client.force_authenticate(user=self.owner)

        list_response = self.client.get(reverse('my-campaign-list'))
        rows = {c['slug']: c for c in list_response.data['data']['campaigns']}
        self.assertEqual(rows[org_campaign.slug]['organization_id'], str(self.org.id))
        self.assertIsNone(rows[solo_campaign.slug]['organization_id'])

        detail_response = self.client.get(reverse('my-campaign-detail', args=[org_campaign.slug]))
        self.assertEqual(detail_response.data['data']['campaign']['organization_id'], str(self.org.id))
        self.assertEqual(detail_response.data['data']['campaign']['organization_name'], self.org.organization_name)

    def test_patch_cannot_reassign_organization_via_organization_id(self):
        # Security regression test: organization_id is write-only at
        # creation time only -- a plain edit must never be able to move a
        # campaign into a different organization, bypassing create_campaign's
        # permission check entirely.
        campaign = make_campaign(owner=self.owner, organization=None)
        other_owner, other_org = make_org_and_owner()
        self.client.force_authenticate(user=self.owner)

        response = self.client.patch(reverse('my-campaign-detail', args=[campaign.slug]), {
            'organization_id': str(other_org.id), 'title': 'Retitled',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        campaign.refresh_from_db()
        self.assertIsNone(campaign.organization)
        self.assertEqual(campaign.title, 'Retitled')


class PayoutOrganizationPermissionTest(APITestCase):
    def setUp(self):
        self.owner, self.org = make_org_and_owner()

    @patch('services.modempay_service.request_disbursement')
    @patch('services.modempay_service.get_balance')
    @patch('services.modempay_service.check_transfer_fee')
    def test_org_member_without_withdraw_funds_is_denied(self, mock_fee, mock_balance, mock_disburse):
        campaign = make_campaign(owner=self.owner, organization=self.org, raised=Decimal('500.00'))
        powerless_member, _ = make_member(self.org, permissions=[])

        with self.assertRaises(PermissionDenied):
            payment_service.request_payout(powerless_member, {
                'campaign_id': campaign.id, 'amount': Decimal('100.00'), 'provider': 'wave', 'phone': '+2207000000',
            })
        mock_disburse.assert_not_called()

    @patch('services.modempay_service.request_disbursement')
    @patch('services.modempay_service.get_balance')
    @patch('services.modempay_service.check_transfer_fee')
    def test_member_with_withdraw_funds_can_request_a_payout(self, mock_fee, mock_balance, mock_disburse):
        mock_fee.return_value = Decimal('1.00')
        mock_balance.return_value = {'available_balance': 1000, 'payout_balance': 1000}
        mock_disburse.return_value = {'id': 'tr_org_1', 'status': 'completed'}
        campaign = make_campaign(owner=self.owner, organization=self.org, raised=Decimal('500.00'))
        treasurer, _ = make_member(self.org, permissions=[OrganizationPermission.WITHDRAW_FUNDS])

        payout = payment_service.request_payout(treasurer, {
            'campaign_id': campaign.id, 'amount': Decimal('100.00'), 'provider': 'wave', 'phone': '+2207000000',
        })
        self.assertEqual(payout.campaign, campaign)

    def test_non_member_gets_404_for_org_campaign_payout(self):
        from django.http import Http404
        campaign = make_campaign(owner=self.owner, organization=self.org, raised=Decimal('500.00'))
        outsider = User.objects.create_user(email='payout-outsider@example.com', password='pass')

        with self.assertRaises(Http404):
            payment_service.request_payout(outsider, {
                'campaign_id': campaign.id, 'amount': Decimal('100.00'), 'provider': 'wave', 'phone': '+2207000000',
            })

    def test_individual_campaign_payout_unaffected_by_org_permissions(self):
        solo_owner = User.objects.create_user(email='solo-payout@example.com', password='pass')
        campaign = make_campaign(owner=solo_owner, organization=None, raised=Decimal('500.00'))
        stranger = User.objects.create_user(email='solo-payout-stranger@example.com', password='pass')

        from django.http import Http404
        with self.assertRaises(Http404):
            payment_service.request_payout(stranger, {
                'campaign_id': campaign.id, 'amount': Decimal('100.00'), 'provider': 'wave', 'phone': '+2207000000',
            })

    def test_any_member_can_view_org_campaign_payout_history(self):
        campaign = make_campaign(owner=self.owner, organization=self.org)
        viewer_member, _ = make_member(self.org, permissions=[])
        # Should not raise -- viewing payout history needs membership only,
        # not a specific permission.
        payouts = payment_service.get_campaign_payouts(viewer_member, campaign.slug)
        self.assertEqual(list(payouts), [])

    def test_non_member_cannot_view_org_campaign_payout_history(self):
        from django.http import Http404
        campaign = make_campaign(owner=self.owner, organization=self.org)
        outsider = User.objects.create_user(email='payout-history-outsider@example.com', password='pass')
        with self.assertRaises(Http404):
            payment_service.get_campaign_payouts(outsider, campaign.slug)


class AdminOrganizationViewsTest(APITestCase):
    """Admin Campaigners page's Organizations tab -- deliberately NOT
    membership-gated (see organization_service.get_all_organizations),
    mirroring how AdminCampaignListView isn't owner-gated."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email='admin@example.com', password='Admin@1234', is_staff=True, role=User.Role.ADMIN,
        )
        self.regular = User.objects.create_user(email='regular@example.com', password='pass')
        self.owner, self.org = make_org_and_owner(organization_name='Gambia Youth Trust')

    def test_regular_user_cannot_list_organizations(self):
        response = self.client.get(reverse('admin-organization-list'))
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
        self.client.force_authenticate(user=self.regular)
        response = self.client.get(reverse('admin-organization-list'))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_list_all_organizations_including_ones_they_dont_belong_to(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse('admin-organization-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [o['organization_name'] for o in response.data['results']]
        self.assertIn('Gambia Youth Trust', names)

    def test_search_matches_organization_name(self):
        make_org_and_owner(organization_name='Basse Health Initiative')
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse('admin-organization-list'), {'search': 'Basse'})
        names = [o['organization_name'] for o in response.data['results']]
        self.assertEqual(names, ['Basse Health Initiative'])

    def test_admin_can_view_any_organization_detail_without_membership(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse('admin-organization-detail', args=[self.org.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['organization']['organization_name'], 'Gambia Youth Trust')

    def test_admin_can_view_any_organization_members_without_membership(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse('admin-organization-member-list', args=[self.org.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        emails = [m['user_email'] for m in response.data['data']['members']]
        self.assertIn(self.owner.email, emails)

    def test_admin_campaign_list_filters_by_organization(self):
        org_campaign = make_campaign(owner=self.owner, organization=self.org)
        solo_campaign = make_campaign(owner=self.owner, organization=None)
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse('admin-campaign-list'), {'organization': str(self.org.id)})
        slugs = [c['slug'] for c in response.data['results']]
        self.assertIn(org_campaign.slug, slugs)
        self.assertNotIn(solo_campaign.slug, slugs)
