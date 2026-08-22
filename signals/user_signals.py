import logging
import traceback

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from apps.users.models import User

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def user_post_save(sender, instance, created, **kwargs):
    if created:
        pass  # Hook for post-registration logic (e.g. create profile, assign default plan)
    sync_role_group_membership(instance)


def sync_role_group_membership(user):
    """Django Group membership is the actual permission-check target now
    (see permissions.roles.user_has_resource) — keep it in sync with the
    `role` field, which stays the single source of truth for a user's
    *identity* (which named role they hold). Runs on every save, but is a
    no-op read-then-compare when membership already matches, so it's cheap
    on the far more common case of a save that didn't touch `role`.
    """
    from django.contrib.auth.models import Group
    from permissions.roles import MANAGED_ROLES

    managed_group_names = set(MANAGED_ROLES)
    current = set(user.groups.filter(name__in=managed_group_names).values_list('name', flat=True))
    target = {user.role} if user.role in managed_group_names else set()
    if current == target:
        return

    stale = current - target
    if stale:
        user.groups.remove(*Group.objects.filter(name__in=stale))
    missing = target - current
    if missing:
        user.groups.add(*[Group.objects.get_or_create(name=name)[0] for name in missing])


@receiver(pre_save, sender=User)
def user_verified_flag_audit(sender, instance, **kwargs):
    """Diagnostic logging for a recurring bug: is_verified has reset itself to
    False multiple times on a live account with no code path we could find
    that explains it. Log every actual change to is_verified with a stack
    trace so the next occurrence is traceable to its real caller instead of
    guessed at.
    """
    if not instance.pk:
        return
    try:
        previous = User.objects.filter(pk=instance.pk).values_list('is_verified', flat=True).first()
    except Exception:
        return
    if previous is not None and previous != instance.is_verified:
        stack = ''.join(traceback.format_stack(limit=8))
        logger.warning(
            'User.is_verified changing for %s: %s -> %s\n%s',
            instance.pk, previous, instance.is_verified, stack,
        )
