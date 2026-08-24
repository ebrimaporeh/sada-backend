from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User
from apps.rbac.models import Role
from permissions.roles import (
    Resource, ALL_RESOURCES,
    get_managed_role_slugs, get_role_resources, set_role_resources,
    get_user_resources, user_has_resource, create_role, delete_role,
)


def authed_client(client, user):
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')


class RoleResourcesTest(APITestCase):
    """permissions.roles' Group/Permission-backed functions -- the actual
    storage for every runtime role's access."""

    def test_default_moderator_resources_match_the_seeded_set(self):
        resources = get_role_resources('moderator')
        self.assertEqual(resources, {
            Resource.CAMPAIGNS_VIEW, Resource.CAMPAIGNS_MODERATE,
            Resource.CATEGORIES_VIEW, Resource.REPORTS_VIEW, Resource.VERIFICATIONS_VIEW,
        })

    def test_default_finance_officer_resources_match_the_seeded_set(self):
        resources = get_role_resources('finance_officer')
        self.assertEqual(resources, {Resource.CAMPAIGNS_VIEW, Resource.DONATIONS_VIEW, Resource.FINANCES_VIEW})

    def test_admin_is_not_a_managed_role(self):
        self.assertNotIn(User.Role.ADMIN, get_managed_role_slugs())
        self.assertEqual(get_role_resources(User.Role.ADMIN), set())

    def test_set_role_resources_replaces_the_set_wholesale(self):
        set_role_resources('moderator', [Resource.AUDIT_VIEW])
        self.assertEqual(get_role_resources('moderator'), {Resource.AUDIT_VIEW})

    def test_set_role_resources_takes_effect_immediately_for_existing_users(self):
        moderator = User.objects.create_user(email='mod@example.com', password='pass', role='moderator')
        self.assertTrue(user_has_resource(moderator, Resource.CAMPAIGNS_VIEW))
        self.assertFalse(user_has_resource(moderator, Resource.FINANCES_VIEW))

        set_role_resources('moderator', [Resource.FINANCES_VIEW])

        # has_perm() caches on the instance (Django's own PermissionsMixin
        # behavior) -- refresh_from_db() doesn't clear that cache, only a
        # *new* instance does, same as what a fresh HTTP request actually
        # gets when auth re-fetches request.user from the DB.
        moderator = User.objects.get(pk=moderator.pk)
        self.assertFalse(user_has_resource(moderator, Resource.CAMPAIGNS_VIEW))
        self.assertTrue(user_has_resource(moderator, Resource.FINANCES_VIEW))

    def test_set_role_resources_drops_unknown_keys_silently(self):
        result = set_role_resources('moderator', [Resource.AUDIT_VIEW, 'not-a-real-resource'])
        self.assertEqual(result, {Resource.AUDIT_VIEW})

    def test_set_role_resources_rejects_a_non_managed_role(self):
        with self.assertRaises(ValueError):
            set_role_resources(User.Role.ADMIN, [Resource.AUDIT_VIEW])

    def test_admin_gets_every_resource_regardless_of_group(self):
        admin = User.objects.create_user(email='admin@example.com', password='pass', role=User.Role.ADMIN)
        self.assertEqual(get_user_resources(admin), ALL_RESOURCES)

    def test_regular_user_gets_no_resources(self):
        user = User.objects.create_user(email='regular@example.com', password='pass', role=User.Role.USER)
        self.assertEqual(get_user_resources(user), set())


class CustomRoleTest(APITestCase):
    """create_role/delete_role -- the ability to define a brand-new staff
    role at runtime, beyond the two that ship by default."""

    def test_create_role_derives_a_slug_and_grants_resources(self):
        role = create_role('Content Reviewer', resources=[Resource.CATEGORIES_VIEW, Resource.CATEGORIES_EDIT])
        self.assertEqual(role.slug, 'content-reviewer')
        self.assertIn(role.slug, get_managed_role_slugs())
        self.assertEqual(get_role_resources(role.slug), {Resource.CATEGORIES_VIEW, Resource.CATEGORIES_EDIT})

    def test_create_role_dedupes_a_colliding_slug(self):
        create_role('Reviewer')
        second = create_role('Reviewer!!')  # slugifies to the same base
        self.assertNotEqual(second.slug, 'reviewer')

    def test_create_role_rejects_a_blank_name(self):
        with self.assertRaises(ValueError):
            create_role('   ')

    def test_a_user_assigned_a_new_custom_role_is_treated_as_staff(self):
        from services.user_service import get_staff_users, get_regular_users
        role = create_role('Content Reviewer')
        user = User.objects.create_user(email='reviewer@example.com', password='pass', role=role.slug)
        self.assertIn(user, get_staff_users())
        self.assertNotIn(user, get_regular_users())

    def test_delete_role_removes_it_and_its_group(self):
        from django.contrib.auth.models import Group
        role = create_role('Temp Role')
        delete_role(role.slug)
        self.assertNotIn(role.slug, get_managed_role_slugs())
        self.assertFalse(Group.objects.filter(name=role.slug).exists())

    def test_delete_role_refused_while_a_user_holds_it(self):
        role = create_role('Sticky Role')
        User.objects.create_user(email='sticky@example.com', password='pass', role=role.slug)
        with self.assertRaises(ValueError):
            delete_role(role.slug)
        self.assertIn(role.slug, get_managed_role_slugs())


class RoleGroupSyncTest(APITestCase):
    """signals/user_signals.py::sync_role_group_membership -- Group
    membership is the actual has_perm() target, and must track `role`."""

    def test_setting_a_managed_role_adds_the_matching_group(self):
        user = User.objects.create_user(email='sync1@example.com', password='pass', role=User.Role.USER)
        user.role = 'moderator'
        user.save()
        self.assertEqual(list(user.groups.values_list('name', flat=True)), ['moderator'])

    def test_reverting_to_a_non_managed_role_removes_the_group(self):
        user = User.objects.create_user(email='sync2@example.com', password='pass', role='moderator')
        self.assertEqual(list(user.groups.values_list('name', flat=True)), ['moderator'])
        user.role = User.Role.USER
        user.save()
        self.assertEqual(list(user.groups.values_list('name', flat=True)), [])

    def test_switching_between_managed_roles_swaps_the_group(self):
        user = User.objects.create_user(email='sync3@example.com', password='pass', role='moderator')
        user.role = 'finance_officer'
        user.save()
        self.assertEqual(list(user.groups.values_list('name', flat=True)), ['finance_officer'])

    def test_a_newly_created_custom_role_gets_group_synced_with_no_extra_code(self):
        role = create_role('Auditor Plus', resources=[Resource.AUDIT_VIEW])
        user = User.objects.create_user(email='sync4@example.com', password='pass', role=role.slug)
        self.assertEqual(list(user.groups.values_list('name', flat=True)), [role.slug])


class UserSerializerResourcesTest(APITestCase):
    def test_resources_field_reflects_the_users_current_role_permissions(self):
        from apps.users.serializers import UserSerializer
        moderator = User.objects.create_user(email='ser-mod@example.com', password='pass', role='moderator')
        data = UserSerializer(moderator).data
        self.assertEqual(set(data['resources']), get_role_resources('moderator'))


class AdminRolePermissionsApiTest(APITestCase):
    """The runtime editor's actual API surface -- list, create, update,
    and delete roles, and confirm a change takes hold for real requests
    immediately, no deploy involved."""

    def setUp(self):
        self.admin = User.objects.create_user(email='rbac-admin@example.com', password='pass', role=User.Role.ADMIN)
        self.moderator = User.objects.create_user(email='rbac-mod@example.com', password='pass', role='moderator')

    def test_list_requires_roles_manage_resource(self):
        authed_client(self.client, self.moderator)
        response = self.client.get('/api/v1/permissions/roles/')
        # Moderators don't have Resource.ROLES_MANAGE by default.
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_list_roles_and_resources(self):
        authed_client(self.client, self.admin)
        response = self.client.get('/api/v1/permissions/roles/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        roles = {r['role']: r['resources'] for r in response.data['data']['roles']}
        self.assertEqual(set(roles['moderator']), get_role_resources('moderator'))
        # Resources come back grouped by entity now, not a flat list.
        groups = response.data['data']['resources']
        all_keys = {action['key'] for group in groups for action in group['actions']}
        self.assertEqual(all_keys, ALL_RESOURCES)

    def test_admin_can_update_a_roles_resources(self):
        authed_client(self.client, self.admin)
        response = self.client.patch(
            '/api/v1/permissions/roles/moderator/', {'resources': [Resource.AUDIT_VIEW]}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(get_role_resources('moderator'), {Resource.AUDIT_VIEW})

    def test_cannot_update_a_non_managed_role(self):
        authed_client(self.client, self.admin)
        response = self.client.patch(
            '/api/v1/permissions/roles/admin/', {'resources': [Resource.AUDIT_VIEW]}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_rejects_an_unknown_resource_key(self):
        authed_client(self.client, self.admin)
        response = self.client.patch(
            '/api/v1/permissions/roles/moderator/', {'resources': ['not-a-real-resource']}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_updated_permissions_take_effect_immediately_on_real_requests(self):
        # Moderator can't see Finances by default.
        authed_client(self.client, self.moderator)
        response = self.client.get('/api/v1/analytics/finance-summary/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Admin grants it at runtime, no deploy.
        authed_client(self.client, self.admin)
        response = self.client.patch(
            '/api/v1/permissions/roles/moderator/',
            {'resources': list(get_role_resources('moderator')) + [Resource.FINANCES_VIEW]},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        # Same moderator, same session, now has access.
        authed_client(self.client, self.moderator)
        response = self.client.get('/api/v1/analytics/finance-summary/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_admin_can_create_a_new_role(self):
        authed_client(self.client, self.admin)
        response = self.client.post(
            '/api/v1/permissions/roles/',
            {'name': 'Content Reviewer', 'resources': [Resource.CATEGORIES_VIEW]},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['data']['role'], 'content-reviewer')
        self.assertTrue(Role.objects.filter(slug='content-reviewer').exists())

    def test_create_role_requires_roles_manage_resource(self):
        authed_client(self.client, self.moderator)
        response = self.client.post('/api/v1/permissions/roles/', {'name': 'Sneaky Role'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Role.objects.filter(name='Sneaky Role').exists())

    def test_create_role_rejects_a_duplicate_name(self):
        authed_client(self.client, self.admin)
        response = self.client.post('/api/v1/permissions/roles/', {'name': 'Moderator'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_can_delete_an_unused_role(self):
        role = create_role('Temp Role')
        authed_client(self.client, self.admin)
        response = self.client.delete(f'/api/v1/permissions/roles/{role.slug}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertFalse(Role.objects.filter(slug=role.slug).exists())

    def test_cannot_delete_a_role_still_in_use(self):
        authed_client(self.client, self.admin)
        response = self.client.delete('/api/v1/permissions/roles/moderator/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Role.objects.filter(slug='moderator').exists())
