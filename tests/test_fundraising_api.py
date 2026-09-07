import io
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import User, Organization
from apps.campaigns.models import Campaign, Category
from apps.fundraising.models import DestinationType, Embed, Poster, ShareLink
from apps.organizations.models import OrganizationType, OrganizationRole, OrganizationMembership
from apps.organizations.permissions import OrganizationPermission
import services.organization_service as organization_service


def make_org_type(**kwargs):
    defaults = {'slug': f'org-type-{OrganizationType.objects.count()}', 'name': 'Community Organization', 'is_visible': True}
    defaults.update(kwargs)
    return OrganizationType.objects.create(**defaults)


def make_org_and_owner(**kwargs):
    org_type = kwargs.pop('org_type', None) or make_org_type()
    user = kwargs.pop('user', None) or User.objects.create_user(
        email=f'owner{User.objects.count()}@example.com', password='pass',
    )
    org = organization_service.create_organization(
        user,
        organization_name=kwargs.pop('organization_name', 'Al-Madina Mosque'),
        organization_type_slug=org_type.slug,
    )
    return user, org


def make_member(org, permissions=None):
    user = User.objects.create_user(email=f'member{User.objects.count()}@example.com', password='pass')
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
        'title': 'Build New Mosque',
        'slug': f'build-new-mosque-{Campaign.objects.count()}',
        'short_description': 'New prayer hall',
        'story': 'Community fundraiser.',
        'goal': Decimal('10000.00'),
        'status': Campaign.Status.ACTIVE,
    }
    defaults.update(kwargs)
    return Campaign.objects.create(**defaults)


class PosterCreateTest(APITestCase):
    def test_campaign_owner_can_create_poster_for_own_campaign(self):
        owner = User.objects.create_user(email='owner@example.com', password='pass')
        campaign = make_campaign(owner=owner)
        self.client.force_authenticate(owner)
        response = self.client.post(reverse('poster-list-create'), {
            'destination_type': DestinationType.CAMPAIGN, 'campaign_id': str(campaign.id),
            'name': 'Ramadan Poster', 'template': Poster.Template.SQUARE,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(ShareLink.objects.filter(poster__name='Ramadan Poster').exists())

    def test_stranger_cannot_create_poster_for_someone_elses_campaign(self):
        campaign = make_campaign()
        stranger = User.objects.create_user(email='stranger@example.com', password='pass')
        self.client.force_authenticate(stranger)
        response = self.client.post(reverse('poster-list-create'), {
            'destination_type': DestinationType.CAMPAIGN, 'campaign_id': str(campaign.id),
            'name': 'Untitled', 'template': Poster.Template.SQUARE,
        })
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_org_member_with_edit_campaign_can_create_poster(self):
        _, org = make_org_and_owner()
        campaign = make_campaign(organization=org)
        member, _ = make_member(org, permissions=[OrganizationPermission.EDIT_CAMPAIGN])
        self.client.force_authenticate(member)
        response = self.client.post(reverse('poster-list-create'), {
            'destination_type': DestinationType.CAMPAIGN, 'campaign_id': str(campaign.id),
            'name': 'Campaign Poster', 'template': Poster.Template.STORY,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_org_member_without_edit_campaign_gets_403(self):
        _, org = make_org_and_owner()
        campaign = make_campaign(organization=org)
        member, _ = make_member(org, permissions=[])
        self.client.force_authenticate(member)
        response = self.client.post(reverse('poster-list-create'), {
            'destination_type': DestinationType.CAMPAIGN, 'campaign_id': str(campaign.id),
            'name': 'Untitled', 'template': Poster.Template.SQUARE,
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_org_admin_can_create_organization_destination_poster(self):
        owner, org = make_org_and_owner()
        self.client.force_authenticate(owner)
        response = self.client.post(reverse('poster-list-create'), {
            'destination_type': DestinationType.ORGANIZATION, 'organization_id': str(org.id),
            'name': 'Homepage Poster', 'template': Poster.Template.WIDE,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['data']['poster']['destination']['type'], DestinationType.ORGANIZATION)

    def test_org_member_without_manage_organization_gets_403_for_org_destination(self):
        _, org = make_org_and_owner()
        member, _ = make_member(org, permissions=[OrganizationPermission.CREATE_CAMPAIGN])
        self.client.force_authenticate(member)
        response = self.client.post(reverse('poster-list-create'), {
            'destination_type': DestinationType.ORGANIZATION, 'organization_id': str(org.id),
            'name': 'Untitled', 'template': Poster.Template.WIDE,
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_member_gets_404_for_organization_destination(self):
        _, org = make_org_and_owner()
        stranger = User.objects.create_user(email='stranger2@example.com', password='pass')
        self.client.force_authenticate(stranger)
        response = self.client.post(reverse('poster-list-create'), {
            'destination_type': DestinationType.ORGANIZATION, 'organization_id': str(org.id),
            'name': 'Untitled', 'template': Poster.Template.WIDE,
        })
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_missing_campaign_id_for_campaign_destination_is_a_validation_error(self):
        owner = User.objects.create_user(email='owner3@example.com', password='pass')
        self.client.force_authenticate(owner)
        response = self.client.post(reverse('poster-list-create'), {
            'destination_type': DestinationType.CAMPAIGN, 'name': 'Untitled', 'template': Poster.Template.SQUARE,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.post(reverse('poster-list-create'), {})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class PosterUpdateDuplicateDeleteTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email='powner@example.com', password='pass')
        self.campaign = make_campaign(owner=self.owner)
        self.client.force_authenticate(self.owner)
        create = self.client.post(reverse('poster-list-create'), {
            'destination_type': DestinationType.CAMPAIGN, 'campaign_id': str(self.campaign.id),
            'name': 'Original', 'template': Poster.Template.SQUARE,
        })
        self.poster_id = create.data['data']['poster']['id']

    def test_owner_can_update_design(self):
        response = self.client.patch(reverse('poster-detail', args=[self.poster_id]), {
            'design': {'version': 1, 'elements': []},
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['data']['poster']['design']['version'], 1)

    def test_owner_can_change_size_mid_edit(self):
        response = self.client.patch(reverse('poster-detail', args=[self.poster_id]), {
            'template': Poster.Template.STORY,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['data']['poster']['template'], Poster.Template.STORY)

    def test_stranger_cannot_update(self):
        stranger = User.objects.create_user(email='pstranger@example.com', password='pass')
        self.client.force_authenticate(stranger)
        response = self.client.patch(reverse('poster-detail', args=[self.poster_id]), {'name': 'Hijacked'})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_duplicate_creates_a_new_poster_with_its_own_share_link(self):
        original_code = Poster.objects.get(pk=self.poster_id).share_link.code
        response = self.client.post(reverse('poster-duplicate', args=[self.poster_id]))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        new_id = response.data['data']['poster']['id']
        self.assertNotEqual(new_id, self.poster_id)
        new_code = Poster.objects.get(pk=new_id).share_link.code
        self.assertNotEqual(new_code, original_code)

    def test_delete_removes_the_poster(self):
        response = self.client.delete(reverse('poster-detail', args=[self.poster_id]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Poster.objects.filter(pk=self.poster_id).exists())

    def test_deleting_the_underlying_draft_campaign_cascades_the_poster(self):
        # delete_campaign() only allows DRAFT/REJECTED campaigns -- exactly
        # the ones that were never public, so cascading their posters away
        # is safe (see fundraising_destination.py's on_delete reasoning).
        import services.campaign_service as campaign_service
        self.campaign.status = Campaign.Status.DRAFT
        self.campaign.save(update_fields=['status'])
        campaign_service.delete_campaign(self.campaign)
        self.assertFalse(Poster.objects.filter(pk=self.poster_id).exists())

    def test_list_only_returns_posters_the_user_can_manage(self):
        other_owner = User.objects.create_user(email='other@example.com', password='pass')
        other_campaign = make_campaign(owner=other_owner)
        self.client.force_authenticate(other_owner)
        self.client.post(reverse('poster-list-create'), {
            'destination_type': DestinationType.CAMPAIGN, 'campaign_id': str(other_campaign.id),
            'name': "Other's Poster", 'template': Poster.Template.SQUARE,
        })
        self.client.force_authenticate(self.owner)
        response = self.client.get(reverse('poster-list-create'))
        names = [p['name'] for p in response.data['results']]
        self.assertIn('Original', names)
        self.assertNotIn("Other's Poster", names)


def make_fake_image_upload(name='test.png'):
    from PIL import Image
    buffer = io.BytesIO()
    Image.new('RGB', (10, 10), color='red').save(buffer, format='PNG')
    buffer.seek(0)
    return SimpleUploadedFile(name, buffer.read(), content_type='image/png')


class PosterImageUploadTest(APITestCase):
    def test_owner_can_upload_an_image_for_the_poster_canvas(self):
        owner = User.objects.create_user(email='imgowner@example.com', password='pass')
        campaign = make_campaign(owner=owner)
        self.client.force_authenticate(owner)
        create = self.client.post(reverse('poster-list-create'), {
            'destination_type': DestinationType.CAMPAIGN, 'campaign_id': str(campaign.id),
            'name': 'Image Poster', 'template': Poster.Template.SQUARE,
        })
        poster_id = create.data['data']['poster']['id']

        response = self.client.post(
            reverse('poster-image-upload', args=[poster_id]),
            {'image': make_fake_image_upload()}, format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertIsNotNone(response.data['data']['image']['image_url'])

    def test_stranger_cannot_upload_an_image(self):
        campaign = make_campaign()
        owner = campaign.owner
        self.client.force_authenticate(owner)
        create = self.client.post(reverse('poster-list-create'), {
            'destination_type': DestinationType.CAMPAIGN, 'campaign_id': str(campaign.id),
            'name': 'Image Poster', 'template': Poster.Template.SQUARE,
        })
        poster_id = create.data['data']['poster']['id']

        stranger = User.objects.create_user(email='imgstranger@example.com', password='pass')
        self.client.force_authenticate(stranger)
        response = self.client.post(
            reverse('poster-image-upload', args=[poster_id]),
            {'image': make_fake_image_upload()}, format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ShareLinkRedirectTest(APITestCase):
    def test_scanning_the_qr_redirects_to_the_current_destination_url(self):
        owner = User.objects.create_user(email='qrowner@example.com', password='pass')
        campaign = make_campaign(owner=owner)
        self.client.force_authenticate(owner)
        create = self.client.post(reverse('poster-list-create'), {
            'destination_type': DestinationType.CAMPAIGN, 'campaign_id': str(campaign.id),
            'name': 'QR Poster', 'template': Poster.Template.SQUARE,
        })
        code = create.data['data']['poster']['share_code']
        self.client.force_authenticate(None)
        response = self.client.get(reverse('fundraising-share-link', args=[code]), follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn(f'/campaigns/{campaign.slug}', response.url)
        share_link = ShareLink.objects.get(code=code)
        self.assertEqual(share_link.click_count, 1)

    def test_unknown_code_404s(self):
        response = self.client.get(reverse('fundraising-share-link', args=['doesnotexist']))
        self.assertEqual(response.status_code, 404)


class EmbedCreateAndLifecycleTest(APITestCase):
    def test_authorized_creation_for_campaign_destination(self):
        owner = User.objects.create_user(email='eowner@example.com', password='pass')
        campaign = make_campaign(owner=owner)
        self.client.force_authenticate(owner)
        response = self.client.post(reverse('embed-list-create'), {
            'destination_type': DestinationType.CAMPAIGN, 'campaign_id': str(campaign.id),
            'name': 'Homepage Widget', 'layout': Embed.Layout.CARD, 'return_url': 'https://example.com',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(response.data['data']['embed']['is_active'])

    def test_authorized_creation_for_organization_destination(self):
        owner, org = make_org_and_owner()
        self.client.force_authenticate(owner)
        response = self.client.post(reverse('embed-list-create'), {
            'destination_type': DestinationType.ORGANIZATION, 'organization_id': str(org.id),
            'name': 'Homepage Widget', 'return_url': 'https://example.com',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_unauthorized_creation_is_rejected(self):
        campaign = make_campaign()
        stranger = User.objects.create_user(email='estranger@example.com', password='pass')
        self.client.force_authenticate(stranger)
        response = self.client.post(reverse('embed-list-create'), {
            'destination_type': DestinationType.CAMPAIGN, 'campaign_id': str(campaign.id), 'name': 'Untitled', 'return_url': 'https://example.com',
        })
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_return_url_persists_and_is_returned(self):
        owner = User.objects.create_user(email='eowner6@example.com', password='pass')
        campaign = make_campaign(owner=owner)
        self.client.force_authenticate(owner)
        create = self.client.post(reverse('embed-list-create'), {
            'destination_type': DestinationType.CAMPAIGN, 'campaign_id': str(campaign.id),
            'name': 'Widget', 'return_url': 'https://example.com/home',
        })
        self.assertEqual(create.data['data']['embed']['return_url'], 'https://example.com/home')

        embed_id = create.data['data']['embed']['id']
        update = self.client.patch(reverse('embed-detail', args=[embed_id]), {
            'return_url': 'https://example.com/other-page',
        }, format='json')
        self.assertEqual(update.status_code, status.HTTP_200_OK, update.data)
        self.assertEqual(update.data['data']['embed']['return_url'], 'https://example.com/other-page')

    def test_invalid_return_url_is_a_validation_error(self):
        owner = User.objects.create_user(email='eowner7@example.com', password='pass')
        campaign = make_campaign(owner=owner)
        self.client.force_authenticate(owner)
        response = self.client.post(reverse('embed-list-create'), {
            'destination_type': DestinationType.CAMPAIGN, 'campaign_id': str(campaign.id),
            'name': 'Widget', 'return_url': 'javascript:alert(1)',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_layout_choice_is_a_validation_error(self):
        owner = User.objects.create_user(email='eowner2@example.com', password='pass')
        campaign = make_campaign(owner=owner)
        self.client.force_authenticate(owner)
        response = self.client.post(reverse('embed-list-create'), {
            'destination_type': DestinationType.CAMPAIGN, 'campaign_id': str(campaign.id),
            'name': 'Untitled', 'layout': 'not-a-real-layout', 'return_url': 'https://example.com',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_deactivate_and_activate_toggle_is_active(self):
        owner = User.objects.create_user(email='eowner3@example.com', password='pass')
        campaign = make_campaign(owner=owner)
        self.client.force_authenticate(owner)
        create = self.client.post(reverse('embed-list-create'), {
            'destination_type': DestinationType.CAMPAIGN, 'campaign_id': str(campaign.id), 'name': 'Widget', 'return_url': 'https://example.com',
        })
        embed_id = create.data['data']['embed']['id']

        deactivate = self.client.post(reverse('embed-deactivate', args=[embed_id]))
        self.assertFalse(deactivate.data['data']['embed']['is_active'])

        activate = self.client.post(reverse('embed-activate', args=[embed_id]))
        self.assertTrue(activate.data['data']['embed']['is_active'])

    def test_duplicate_creates_an_inactive_copy(self):
        owner = User.objects.create_user(email='eowner4@example.com', password='pass')
        campaign = make_campaign(owner=owner)
        self.client.force_authenticate(owner)
        create = self.client.post(reverse('embed-list-create'), {
            'destination_type': DestinationType.CAMPAIGN, 'campaign_id': str(campaign.id), 'name': 'Widget', 'return_url': 'https://example.com',
        })
        embed_id = create.data['data']['embed']['id']
        response = self.client.post(reverse('embed-duplicate', args=[embed_id]))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertFalse(response.data['data']['embed']['is_active'])

    def test_delete_removes_the_embed(self):
        owner = User.objects.create_user(email='eowner5@example.com', password='pass')
        campaign = make_campaign(owner=owner)
        self.client.force_authenticate(owner)
        create = self.client.post(reverse('embed-list-create'), {
            'destination_type': DestinationType.CAMPAIGN, 'campaign_id': str(campaign.id), 'name': 'Widget', 'return_url': 'https://example.com',
        })
        embed_id = create.data['data']['embed']['id']
        response = self.client.delete(reverse('embed-detail', args=[embed_id]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Embed.objects.filter(pk=embed_id).exists())


class EmbedPublicViewTest(APITestCase):
    def test_public_endpoint_requires_no_auth_and_returns_destination_info(self):
        owner = User.objects.create_user(email='epub@example.com', password='pass')
        campaign = make_campaign(owner=owner, goal=Decimal('5000.00'), raised=Decimal('1000.00'))
        self.client.force_authenticate(owner)
        create = self.client.post(reverse('embed-list-create'), {
            'destination_type': DestinationType.CAMPAIGN, 'campaign_id': str(campaign.id), 'name': 'Widget', 'return_url': 'https://example.com',
        })
        embed_id = create.data['data']['embed']['id']

        self.client.force_authenticate(None)
        response = self.client.get(reverse('embed-public', args=[embed_id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        destination = response.data['data']['embed']['destination']
        self.assertEqual(destination['title'], campaign.title)
        self.assertEqual(Decimal(destination['goal']), Decimal('5000.00'))
        self.assertIn('donation_url', destination)

    def test_inactive_embed_still_renders_publicly_with_is_active_false(self):
        owner = User.objects.create_user(email='epub2@example.com', password='pass')
        campaign = make_campaign(owner=owner)
        self.client.force_authenticate(owner)
        create = self.client.post(reverse('embed-list-create'), {
            'destination_type': DestinationType.CAMPAIGN, 'campaign_id': str(campaign.id), 'name': 'Widget', 'return_url': 'https://example.com',
        })
        embed_id = create.data['data']['embed']['id']
        self.client.post(reverse('embed-deactivate', args=[embed_id]))

        self.client.force_authenticate(None)
        response = self.client.get(reverse('embed-public', args=[embed_id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['data']['embed']['is_active'])

    def test_open_ended_campaign_shows_no_deadline_and_is_ongoing(self):
        owner = User.objects.create_user(email='epub3@example.com', password='pass')
        campaign = make_campaign(owner=owner, deadline=None)
        self.client.force_authenticate(owner)
        create = self.client.post(reverse('embed-list-create'), {
            'destination_type': DestinationType.CAMPAIGN, 'campaign_id': str(campaign.id), 'name': 'Widget', 'return_url': 'https://example.com',
        })
        embed_id = create.data['data']['embed']['id']

        self.client.force_authenticate(None)
        response = self.client.get(reverse('embed-public', args=[embed_id]))
        destination = response.data['data']['embed']['destination']
        self.assertIsNone(destination['deadline'])
        self.assertTrue(destination['is_ongoing'])
