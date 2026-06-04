from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.users.models import User


@receiver(post_save, sender=User)
def user_post_save(sender, instance, created, **kwargs):
    if created:
        pass  # Hook for post-registration logic (e.g. create profile, assign default plan)
