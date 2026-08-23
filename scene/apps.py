from django.apps import AppConfig
from django.db.models.signals import post_migrate


class SceneConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'scene'

    def ready(self):
        # Set global admin changelist pagination limit
        from django.contrib.admin import ModelAdmin as DjangoModelAdmin
        DjangoModelAdmin.list_per_page = 30
        try:
            from unfold.admin import ModelAdmin as UnfoldModelAdmin
            UnfoldModelAdmin.list_per_page = 30
        except ImportError:
            pass

        # Import signals module to ensure receivers are connected
        from agent.signals import sync_categories
        post_migrate.connect(sync_categories, sender=self)