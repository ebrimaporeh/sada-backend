from decimal import Decimal
from django.urls import reverse
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import User
from apps.campaigns.models import Campaign, Category
from apps.vision.models import VisionTopic


def make_campaign(**kwargs):
    owner = kwargs.pop('owner', None) or User.objects.create_user(
        email=f'seo-owner{User.objects.count()}@example.com', password='pass',
    )
    category = kwargs.pop('category', None) or Category.objects.create(name=f'Cat {Category.objects.count()}')
    defaults = {
        'owner': owner,
        'category': category,
        'title': 'Well for Bakau',
        'slug': f'well-for-bakau-{Campaign.objects.count()}',
        'short_description': 'Clean water for the community.',
        'story': 'A well for the community.',
        'goal': Decimal('10000.00'),
        'status': Campaign.Status.ACTIVE,
    }
    defaults.update(kwargs)
    return Campaign.objects.create(**defaults)


@override_settings(FRONTEND_URL='https://example-frontend.test')
class CampaignSharePreviewTest(APITestCase):
    def test_public_campaign_renders_real_og_tags(self):
        campaign = make_campaign(title='Flood Relief', short_description='Help families in Basse.')
        url = reverse('share-campaign', kwargs={'slug': campaign.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.content.decode()
        self.assertIn('<meta property="og:title" content="Flood Relief">', body)
        self.assertIn('Help families in Basse.', body)
        self.assertIn(f'https://example-frontend.test/campaigns/{campaign.slug}', body)

    def test_draft_campaign_does_not_leak_data_and_redirects_instead(self):
        # A campaign that isn't public yet (draft/pending/rejected/suspended)
        # must never have its title/description/image rendered here --
        # this endpoint has no auth check of its own, unlike the API.
        campaign = make_campaign(title='Secret Draft Campaign', status=Campaign.Status.DRAFT)
        url = reverse('share-campaign', kwargs={'slug': campaign.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertNotIn(b'Secret Draft Campaign', response.content)
        self.assertEqual(response.url, f'https://example-frontend.test/campaigns/{campaign.slug}')

    def test_unknown_slug_redirects_without_erroring(self):
        url = reverse('share-campaign', kwargs={'slug': 'does-not-exist'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)

    def test_html_in_campaign_title_is_escaped_not_injected(self):
        # Campaign titles are user-supplied at creation time and this page
        # is rendered for anyone (including bots) with no auth -- a title
        # designed to break out of the meta content="" attribute must not
        # be able to inject markup/script into this public page.
        campaign = make_campaign(title='"><script>alert(1)</script>')
        url = reverse('share-campaign', kwargs={'slug': campaign.slug})
        response = self.client.get(url)
        body = response.content.decode()
        self.assertNotIn('<script>alert(1)</script>', body)
        self.assertIn('&lt;script&gt;', body)


@override_settings(FRONTEND_URL='https://example-frontend.test')
class SitemapTest(APITestCase):
    def test_includes_active_campaign_excludes_draft(self):
        active = make_campaign(status=Campaign.Status.ACTIVE)
        make_campaign(status=Campaign.Status.DRAFT, slug='hidden-draft')
        response = self.client.get(reverse('sitemap'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/xml')
        body = response.content.decode()
        self.assertIn(f'/campaigns/{active.slug}', body)
        self.assertNotIn('hidden-draft', body)

    def test_includes_static_pages(self):
        response = self.client.get(reverse('sitemap'))
        body = response.content.decode()
        self.assertIn('https://example-frontend.test/campaigns</loc>', body)
        self.assertIn('https://example-frontend.test/</loc>', body)


@override_settings(FRONTEND_URL='https://example-frontend.test')
class CampaignerSharePreviewTest(APITestCase):
    def test_public_campaigner_renders_real_og_tags(self):
        owner = User.objects.create_user(email='campaigner@example.com', password='pass', bio='Community organizer.')
        make_campaign(owner=owner, is_anonymous=False)  # makes them a "campaigner" at all
        url = reverse('share-campaigner', kwargs={'id': owner.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.content.decode()
        self.assertIn(owner.full_name, body)
        self.assertIn('Community organizer.', body)
        self.assertIn(f'https://example-frontend.test/campaigners/{owner.id}', body)

    def test_user_with_no_public_campaigns_redirects_without_leaking_data(self):
        # Not a "campaigner" at all (no public campaign) -- nothing to show.
        private_user = User.objects.create_user(email='private@example.com', password='pass', first_name='Private')
        url = reverse('share-campaigner', kwargs={'id': private_user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertNotIn(b'Private', response.content)


@override_settings(FRONTEND_URL='https://example-frontend.test')
class VisionTopicSharePreviewTest(APITestCase):
    def test_published_topic_renders_real_og_tags(self):
        topic = VisionTopic.objects.create(
            title='Investment Platform', summary='Where the investment side of the platform is headed.',
            is_published=True,
        )
        url = reverse('share-vision-topic', kwargs={'slug': topic.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.content.decode()
        self.assertIn('Investment Platform', body)
        self.assertIn(f'https://example-frontend.test/vision/{topic.slug}', body)

    def test_unpublished_topic_redirects_without_leaking_data(self):
        topic = VisionTopic.objects.create(title='Secret Draft Topic', is_published=False)
        url = reverse('share-vision-topic', kwargs={'slug': topic.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertNotIn(b'Secret Draft Topic', response.content)


class RobotsTxtTest(APITestCase):
    def test_disallows_everything_on_the_api_domain(self):
        response = self.client.get(reverse('robots-txt'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'text/plain')
        self.assertIn('Disallow: /', response.content.decode())
