from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User
from permissions.roles import (
    Resource, ALL_RESOURCES, MANAGED_ROLES,
    get_role_resources, set_role_resources, get_user_resources, user_has_resource,
)


def authed_client(client, user):
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')


class RoleResourcesTest(APITestCase):
    """permissions.roles' Group/Permission-backed functions -- the actual
    storage for MANAGED_ROLES' access, replacing the old hardcoded dict."""

    def test_default_moderator_resources_match_the_old_hardcoded_set(self):
        resources = get_role_resources(User.Role.MODERATOR)
        self.assertEqual(resources, {
            Resource.CAMPAIGNS_VIEW, Resource.CAMPAIGNS_MODERATE,
            Resource.CATEGORIES, Resource.REPORTS, Resource.VERIFICATIONS,
        })

    def test_default_finance_officer_resources_match_the_old_hardcoded_set(self):
        resources = get_role_resources(User.Role.FINANCE_OFFICER)
        self.assertEqual(resources, {Resource.CAMPAIGNS_VIEW, Resource.DONATIONS, Resource.FINANCES})

    def test_admin_is_not_a_managed_role(self):
        self.assertNotIn(User.Role.ADMIN, MANAGED_ROLES)
        self.assertEqual(get_role_resources(User.Role.ADMIN), set())

    def test_set_role_resources_replaces_the_set_wholesale(self):
        set_role_resources(User.Role.MODERATOR, [Resource.AUDIT])
        self.assertEqual(get_role_resources(User.Role.MODERATOR), {Resource.AUDIT})

    def test_set_role_resources_takes_effect_immediately_for_existing_users(self):
        moderator = User.objects.create_user(email='mod@example.com', password='pass', role=User.Role.MODERATOR)
        self.assertTrue(user_has_resource(moderator, Resource.CAMPAIGNS_VIEW))
        self.assertFalse(user_has_resource(moderator, Resource.FINANCES))

        set_role_resources(User.Role.MODERATOR, [Resource.FINANCES])

        # has_perm() caches on the instance (Django's own PermissionsMixin
        # behavior) -- refresh_from_db() doesn't clear that cache, only a
        # *new* instance does, same as what a fresh HTTP request actually
        # gets when auth re-fetches request.user from the DB.
        moderator = User.objects.get(pk=moderator.pk)
        self.assertFalse(user_has_resource(moderator, Resource.CAMPAIGNS_VIEW))
        self.assertTrue(user_has_resource(moderator, Resource.FINANCES))

    def test_set_role_resources_drops_unknown_keys_silently(self):
        result = set_role_resources(User.Role.MODERATOR, [Resource.AUDIT, 'not-a-real-resource'])
        self.assertEqual(result, {Resource.AUDIT})

    def test_set_role_resources_rejects_a_non_managed_role(self):
        with self.assertRaises(ValueError):
            set_role_resources(User.Role.ADMIN, [Resource.AUDIT])

    def test_admin_gets_every_resource_regardless_of_group(self):
        admin = User.objects.create_user(email='admin@example.com', password='pass', role=User.Role.ADMIN)
        self.assertEqual(get_user_resources(admin), ALL_RESOURCES)

    def test_regular_user_gets_no_resources(self):
        user = User.objects.create_user(email='regular@example.com', password='pass', role=User.Role.USER)
        self.assertEqual(get_user_resources(user), set())


class RoleGroupSyncTest(APITestCase):
    """signals/user_signals.py::sync_role_group_membership -- Group
    membership is the actual has_perm() target, and must track `role`."""

    def test_setting_a_managed_role_adds_the_matching_group(self):
        user = User.objects.create_user(email='sync1@example.com', password='pass', role=User.Role.USER)
        user.role = User.Role.MODERATOR
        user.save()
        self.assertEqual(list(user.groups.values_list('name', flat=True)), [User.Role.MODERATOR])

    def test_reverting_to_a_non_managed_role_removes_the_group(self):
        user = User.objects.create_user(email='sync2@example.com', password='pass', role=User.Role.MODERATOR)
        self.assertEqual(list(user.groups.values_list('name', flat=True)), [User.Role.MODERATOR])
        user.role = User.Role.USER
        user.save()
        self.assertEqual(list(user.groups.values_list('name', flat=True)), [])

    def test_switching_between_managed_roles_swaps_the_group(self):
        user = User.objects.create_user(email='sync3@example.com', password='pass', role=User.Role.MODERATOR)
        user.role = User.Role.FINANCE_OFFICER
        user.save()
        self.assertEqual(list(user.groups.values_list('name', flat=True)), [User.Role.FINANCE_OFFICER])


class UserSerializerResourcesTest(APITestCase):
    def test_resources_field_reflects_the_users_current_role_permissions(self):
        from apps.users.serializers import UserSerializer
        moderator = User.objects.create_user(email='ser-mod@example.com', password='pass', role=User.Role.MODERATOR)
        data = UserSerializer(moderator).data
        self.assertEqual(set(data['resources']), get_role_resources(User.Role.MODERATOR))


class AdminRolePermissionsApiTest(APITestCase):
    """The runtime editor's actual API surface -- GET the current state,
    PATCH a role's resources, and confirm the change takes hold for real
    requests immediately, no deploy involved."""

    def setUp(self):
        self.admin = User.objects.create_user(email='rbac-admin@example.com', password='pass', role=User.Role.ADMIN)
        self.moderator = User.objects.create_user(email='rbac-mod@example.com', password='pass', role=User.Role.MODERATOR)

    def test_list_requires_staff_resource(self):
        authed_client(self.client, self.moderator)
        response = self.client.get('/api/v1/permissions/roles/')
        # Moderators don't have Resource.STAFF by default.
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_list_roles_and_resources(self):
        authed_client(self.client, self.admin)
        response = self.client.get('/api/v1/permissions/roles/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        roles = {r['role']: r['resources'] for r in response.data['data']['roles']}
        self.assertEqual(set(roles['moderator']), get_role_resources(User.Role.MODERATOR))
        resource_keys = {r['key'] for r in response.data['data']['resources']}
        self.assertEqual(resource_keys, ALL_RESOURCES)

    def test_admin_can_update_a_roles_resources(self):
        authed_client(self.client, self.admin)
        response = self.client.patch(
            '/api/v1/permissions/roles/moderator/', {'resources': [Resource.AUDIT]}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(get_role_resources(User.Role.MODERATOR), {Resource.AUDIT})

    def test_cannot_update_a_non_managed_role(self):
        authed_client(self.client, self.admin)
        response = self.client.patch(
            '/api/v1/permissions/roles/admin/', {'resources': [Resource.AUDIT]}, format='json',
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
            {'resources': list(get_role_resources(User.Role.MODERATOR)) + [Resource.FINANCES]},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        # Same moderator, same session, now has access.
        authed_client(self.client, self.moderator)
        response = self.client.get('/api/v1/analytics/finance-summary/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
