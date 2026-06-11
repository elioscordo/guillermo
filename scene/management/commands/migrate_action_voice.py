from django.core.management.base import BaseCommand
from django.db import transaction
from scene.models import Action

class Command(BaseCommand):
    help = 'Migrates the text field into the prompt_voice field for all Action objects'

    def handle(self, *args, **options):
        # Filter actions that actually have text to migrate
        actions = Action.objects.exclude(text__isnull=True).exclude(text="")
        total = actions.count()

        if total == 0:
            self.stdout.write(self.style.WARNING("No actions found with text to migrate."))
            return

        self.stdout.write(f"Starting migration of {total} actions...")

        with transaction.atomic():
            for action in actions:
                current_voice = action.prompt_voice or ""
                text_content = action.text or ""
                
                # Apply formatting: <prompt_voice>text
                action.prompt_voice = f"<{current_voice}>{text_content}"
                action.save(update_fields=['prompt_voice'])

        self.stdout.write(
            self.style.SUCCESS(f"Successfully migrated {total} actions.")
        )