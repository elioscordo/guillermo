from django.core.management.base import BaseCommand
from django.db import connection
from django.apps import apps
from django.db.utils import ProgrammingError

class Command(BaseCommand):
    help = 'Renames the "action" model and its database table to "shot".'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Attempting to rename model "Action" to "Shot" and its database table...'))

        old_table_name = 'scene_action'
        new_table_name = 'scene_shot'

        try:
            # Check if the old table exists
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT 1 FROM information_schema.tables WHERE table_name = '{old_table_name}';")
                if not cursor.fetchone():
                    self.stdout.write(self.style.SUCCESS(f'Table "{old_table_name}" does not exist. Assuming rename already happened or was never created.'))
                    return

            # Rename the table
            with connection.cursor() as cursor:
                self.stdout.write(f'Renaming table "{old_table_name}" to "{new_table_name}"...')
                cursor.execute(f'ALTER TABLE "{old_table_name}" RENAME TO "{new_table_name}";')
                self.stdout.write(self.style.SUCCESS(f'Successfully renamed table "{old_table_name}" to "{new_table_name}".'))

            # Rename ManyToMany tables if they exist (e.g., scene_action_props -> scene_shot_props)
            m2m_tables = [('scene_action_props', 'scene_shot_props'), ('scene_action_cast', 'scene_shot_cast')]
            with connection.cursor() as cursor:
                for old_m2m, new_m2m in m2m_tables:
                    cursor.execute(f"SELECT 1 FROM information_schema.tables WHERE table_name = '{old_m2m}';")
                    if cursor.fetchone():
                        self.stdout.write(f'Renaming M2M table "{old_m2m}" to "{new_m2m}"...')
                        cursor.execute(f'ALTER TABLE "{old_m2m}" RENAME TO "{new_m2m}";')

            # Update content types (important for Django Admin and permissions)
            ContentType = apps.get_model('contenttypes', 'ContentType')
            try:
                ct = ContentType.objects.get(app_label='scene', model='action')
                ct.model = 'shot'
                ct.save()
                self.stdout.write(self.style.SUCCESS('Successfully updated ContentType for "action" to "shot".'))
            except ContentType.DoesNotExist:
                self.stdout.write(self.style.WARNING('ContentType for "action" not found.'))

            self.stdout.write(self.style.SUCCESS('Model and table renaming process completed.'))

        except ProgrammingError as e:
            self.stdout.write(self.style.ERROR(f'Database error during rename: {e}'))
            self.stdout.write(self.style.ERROR('Please ensure you have appropriate database permissions and that the table is not locked.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'An unexpected error occurred: {e}'))