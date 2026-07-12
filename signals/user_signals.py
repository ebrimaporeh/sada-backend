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
