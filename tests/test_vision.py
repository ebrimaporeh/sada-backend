from rest_framework import status
from rest_framework.test import APITestCase

from apps.vision.models import VisionTopic


def make_topic(**kwargs):
    defaults = {
        'title': f'Topic {VisionTopic.objects.count()}',
        'is_published': True,
    }
    defaults.update(kwargs)
    return VisionTopic.objects.create(**defaults)


class VisionTopicModelTest(APITestCase):
    def test_slug_auto_generates_from_title(self):
        topic = make_topic(title='Entity & Account Architecture')
        self.assertEqual(topic.slug, 'entity-account-architecture')

    def test_slug_collision_gets_suffixed(self):
        first = make_topic(title='Investment Platform')
        second = make_topic(title='Investment Platform')
        self.assertEqual(first.slug, 'investment-platform')
        self.assertEqual(second.slug, 'investment-platform-1')

    def test_explicit_slug_is_not_overwritten(self):
        topic = make_topic(title='Something', slug='custom-slug')
        self.assertEqual(topic.slug, 'custom-slug')


class PublicVisionTopicViewTest(APITestCase):
    def test_list_only_returns_published_topics(self):
        published = make_topic(title='Published', is_published=True)
        make_topic(title='Draft', is_published=False)

        response = self.client.get('/api/v1/vision/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = [t['slug'] for t in response.data['data']['topics']]
        self.assertEqual(slugs, [published.slug])

    def test_list_excludes_body_fields(self):
        make_topic(title='Lean', is_published=True, current_state='Long document body')
        response = self.client.get('/api/v1/vision/')
        topic_data = response.data['data']['topics'][0]
        self.assertNotIn('current_state', topic_data)
        self.assertIn('summary', topic_data)

    def test_detail_returns_a_published_topic(self):
        topic = make_topic(title='Detail Me', is_published=True, current_state='The current state.')
        response = self.client.get(f'/api/v1/vision/{topic.slug}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['topic']['current_state'], 'The current state.')

    def test_detail_404s_for_a_draft(self):
        topic = make_topic(title='Still Drafting', is_published=False)
        response = self.client.get(f'/api/v1/vision/{topic.slug}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_404s_for_an_unknown_slug(self):
        response = self.client.get('/api/v1/vision/does-not-exist/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class AdminVisionTopicViewTest(APITestCase):
    def test_list_requires_admin(self):
        response = self.client.get('/api/v1/vision/admin/')
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_create_requires_admin(self):
        response = self.client.post('/api/v1/vision/admin/', {'title': 'New Topic'})
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_update_requires_admin(self):
        topic = make_topic()
        response = self.client.patch(f'/api/v1/vision/admin/{topic.slug}/', {'title': 'Renamed'})
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_delete_requires_admin(self):
        topic = make_topic()
        response = self.client.delete(f'/api/v1/vision/admin/{topic.slug}/')
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
