import io
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import User, Organization
from apps.campaigns.models import Campaign, Category
from apps.design_studio.models import DestinationType, Embed, Poster, ShareLink
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

    def test_cannot_create_a_second_poster_for_the_same_campaign(self):
        # One poster per destination now covers all three layouts itself
        # (see Poster's own docstring) -- a second create attempt for a
        # destination that already has one is a conflict, not a way to get
        # an alternate design.
        response = self.client.post(reverse('poster-list-create'), {
            'destination_type': DestinationType.CAMPAIGN, 'campaign_id': str(self.campaign.id),
            'name': 'Second', 'template': Poster.Template.SQUARE,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(Poster.objects.filter(campaign=self.campaign).count(), 1)

    def test_delete_removes_the_poster(self):
        response = self.client.delete(reverse('poster-detail', args=[self.poster_id]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Poster.objects.filter(pk=self.poster_id).exists())

    def test_deleting_the_underlying_draft_campaign_cascades_the_poster(self):
        # delete_campaign() only allows DRAFT/REJECTED campaigns -- exactly
        # the ones that were never public, so cascading their posters away
        # is safe (see design_studio_destination.py's on_delete reasoning).
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
        response = self.client.get(reverse('design-studio-share-link', args=[code]), follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn(f'/campaigns/{campaign.slug}', response.url)
        share_link = ShareLink.objects.get(code=code)
        self.assertEqual(share_link.click_count, 1)

    def test_unknown_code_404s(self):
        response = self.client.get(reverse('design-studio-share-link', args=['doesnotexist']))
        self.assertEqual(response.status_code, 404)


class OrganizationEmbedGetOrCreateTest(APITestCase):
    def test_org_admin_gets_or_creates_the_embed(self):
        owner, org = make_org_and_owner()
        self.client.force_authenticate(owner)
        response = self.client.get(reverse('organization-embed', args=[org.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['data']['embed']['organization']['id'], str(org.id))
        self.assertTrue(response.data['data']['embed']['is_active'])

    def test_calling_it_twice_returns_the_same_embed(self):
        owner, org = make_org_and_owner()
        self.client.force_authenticate(owner)
        first = self.client.get(reverse('organization-embed', args=[org.id]))
        second = self.client.get(reverse('organization-embed', args=[org.id]))
        self.assertEqual(first.data['data']['embed']['id'], second.data['data']['embed']['id'])
        self.assertEqual(Embed.objects.filter(organization=org).count(), 1)

    def test_member_with_manage_organization_can_access(self):
        _, org = make_org_and_owner()
        member, _ = make_member(org, permissions=[OrganizationPermission.MANAGE_ORGANIZATION])
        self.client.force_authenticate(member)
        response = self.client.get(reverse('organization-embed', args=[org.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_member_without_manage_organization_gets_403(self):
        _, org = make_org_and_owner()
        member, _ = make_member(org, permissions=[OrganizationPermission.CREATE_CAMPAIGN])
        self.client.force_authenticate(member)
        response = self.client.get(reverse('organization-embed', args=[org.id]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_member_gets_404(self):
        _, org = make_org_and_owner()
        stranger = User.objects.create_user(email='estranger@example.com', password='pass')
        self.client.force_authenticate(stranger)
        response = self.client.get(reverse('organization-embed', args=[org.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_request_is_rejected(self):
        _, org = make_org_and_owner()
        response = self.client.get(reverse('organization-embed', args=[org.id]))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class EmbedUpdateAndLifecycleTest(APITestCase):
    def setUp(self):
        self.owner, self.org = make_org_and_owner()
        self.client.force_authenticate(self.owner)
        get = self.client.get(reverse('organization-embed', args=[self.org.id]))
        self.embed_id = get.data['data']['embed']['id']

    def test_owner_can_update_layout_configuration_and_return_url(self):
        response = self.client.patch(reverse('embed-detail', args=[self.embed_id]), {
            'layout': Embed.Layout.WIDE,
            'configuration': {'appearance': {'buttonColor': '#123456'}},
            'return_url': 'https://example.com/home',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['data']['embed']['layout'], Embed.Layout.WIDE)
        self.assertEqual(response.data['data']['embed']['return_url'], 'https://example.com/home')

    def test_invalid_return_url_is_a_validation_error(self):
        response = self.client.patch(reverse('embed-detail', args=[self.embed_id]), {
            'return_url': 'javascript:alert(1)',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_layout_choice_is_a_validation_error(self):
        response = self.client.patch(reverse('embed-detail', args=[self.embed_id]), {
            'layout': 'not-a-real-layout',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_stranger_cannot_update(self):
        # Not a member at all -- check_destination_manage_access's
        # anti-enumeration split treats "no membership" as 404, not 403
        # (see its own docstring: the caller is probing an opaque embed id
        # that could belong to any organization).
        stranger = User.objects.create_user(email='estranger2@example.com', password='pass')
        self.client.force_authenticate(stranger)
        response = self.client.patch(reverse('embed-detail', args=[self.embed_id]), {'name': 'Hijacked'})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_deactivate_and_activate_toggle_is_active(self):
        deactivate = self.client.post(reverse('embed-deactivate', args=[self.embed_id]))
        self.assertFalse(deactivate.data['data']['embed']['is_active'])

        activate = self.client.post(reverse('embed-activate', args=[self.embed_id]))
        self.assertTrue(activate.data['data']['embed']['is_active'])


class EmbedPublicViewTest(APITestCase):
    def setUp(self):
        self.owner, self.org = make_org_and_owner()
        self.client.force_authenticate(self.owner)
        get = self.client.get(reverse('organization-embed', args=[self.org.id]))
        self.embed_id = get.data['data']['embed']['id']

    def test_public_endpoint_requires_no_auth_and_returns_gallery(self):
        campaign = make_campaign(
            organization=self.org, show_in_embed=True, goal=Decimal('5000.00'), raised=Decimal('1000.00'),
        )
        self.org.show_in_embed = True
        self.org.save(update_fields=['show_in_embed'])

        self.client.force_authenticate(None)
        response = self.client.get(reverse('embed-public', args=[self.embed_id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        embed = response.data['data']['embed']
        self.assertEqual(embed['organization']['id'], str(self.org.id))
        destinations = embed['destinations']
        self.assertEqual(len(destinations), 2)
        types = {d['type'] for d in destinations}
        self.assertEqual(types, {DestinationType.ORGANIZATION, DestinationType.CAMPAIGN})
        campaign_destination = next(d for d in destinations if d['type'] == DestinationType.CAMPAIGN)
        self.assertEqual(campaign_destination['title'], campaign.title)
        self.assertEqual(Decimal(campaign_destination['goal']), Decimal('5000.00'))
        self.assertIn('donation_url', campaign_destination)

    def test_gallery_excludes_non_active_or_opted_out_campaigns(self):
        # Organization.show_in_embed defaults True -- opt it out here so
        # this test isolates the campaign-side filtering it's named for.
        self.org.show_in_embed = False
        self.org.save(update_fields=['show_in_embed'])
        make_campaign(organization=self.org, show_in_embed=False, status=Campaign.Status.ACTIVE)
        make_campaign(organization=self.org, show_in_embed=True, status=Campaign.Status.DRAFT)

        response = self.client.get(reverse('embed-public', args=[self.embed_id]))
        self.assertEqual(response.data['data']['embed']['destinations'], [])

    def test_layout_query_param_overrides_the_stored_default(self):
        # The embed's own stored layout defaults to CARD (see Embed.layout) --
        # a ?layout= override lets the same embed be installed elsewhere on
        # the org's site with a different layout, without changing that
        # stored default or needing a second Embed.
        response = self.client.get(reverse('embed-public', args=[self.embed_id]), {'layout': Embed.Layout.WIDE})
        self.assertEqual(response.data['data']['embed']['layout'], Embed.Layout.WIDE)

        unchanged = self.client.get(reverse('embed-public', args=[self.embed_id]))
        self.assertEqual(unchanged.data['data']['embed']['layout'], Embed.Layout.CARD)
        self.assertEqual(Embed.objects.get(pk=self.embed_id).layout, Embed.Layout.CARD)

    def test_unrecognized_layout_query_param_falls_back_to_the_stored_default(self):
        response = self.client.get(reverse('embed-public', args=[self.embed_id]), {'layout': 'not-a-real-layout'})
        self.assertEqual(response.data['data']['embed']['layout'], Embed.Layout.CARD)

    def test_inactive_embed_still_renders_publicly_with_is_active_false(self):
        self.client.post(reverse('embed-deactivate', args=[self.embed_id]))

        self.client.force_authenticate(None)
        response = self.client.get(reverse('embed-public', args=[self.embed_id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['data']['embed']['is_active'])

    def test_open_ended_campaign_shows_no_deadline_and_is_ongoing(self):
        # Opt the organization itself out so destinations[0] is unambiguously
        # the campaign this test is about, not the org's own (also
        # deadline-less) card.
        self.org.show_in_embed = False
        self.org.save(update_fields=['show_in_embed'])
        make_campaign(organization=self.org, show_in_embed=True, deadline=None)

        self.client.force_authenticate(None)
        response = self.client.get(reverse('embed-public', args=[self.embed_id]))
        destination = response.data['data']['embed']['destinations'][0]
        self.assertEqual(destination['type'], DestinationType.CAMPAIGN)
        self.assertIsNone(destination['deadline'])
        self.assertTrue(destination['is_ongoing'])
