from django.apps import apps
from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.contrib.auth import get_user_model
from django.dispatch import receiver
from .models import AgentProfile, PromptCategory

@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        AgentProfile.objects.create(user=instance)


def sync_categories(sender, **kwargs):
    """
    Iterates over all models in all installed apps after migrations run.
    If a model defines a static category method, run it to sync rows.
    """
    for model in apps.get_models():
        cat_func = getattr(model, "sync_prompt_categories", None)
        if callable(cat_func):
            try:
                for cat_data in (cat_func() or []):
                    if isinstance(cat_data, (list, tuple)) and len(cat_data) >= 2:
                        PromptCategory.objects.get_or_create(
                            slug=cat_data[0],
                            defaults={'name': cat_data[1]}
                        )
                    elif isinstance(cat_data, str):
                        PromptCategory.objects.get_or_create(
                            slug=cat_data,
                            defaults={'name': cat_data}
                        )
            except Exception:
                continue

