from django.db.models.signals import post_save
from django.conf import settings
from django.dispatch import receiver

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_profile(sender, instance, created, **kwargs):
    if created:
        # Local import to prevent circular dependencies during app registry loading
        from .models import StoryProfile
        # get_or_create prevents errors if a profile was manually created elsewhere
        StoryProfile.objects.get_or_create(user=instance)
