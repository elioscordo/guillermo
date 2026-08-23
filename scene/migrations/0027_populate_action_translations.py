from django.db import migrations
from django.db.models import F


def populate_translations(apps, schema_editor):
    Action = apps.get_model('scene', 'Action')
    Action.objects.filter(prompt_voice_en__isnull=True).exclude(prompt_voice__isnull=True).update(
        prompt_voice_en=F('prompt_voice')
    )
    Action.objects.filter(prompt_comic_en__isnull=True).exclude(prompt_comic__isnull=True).update(
        prompt_comic_en=F('prompt_comic')
    )
    Action.objects.filter(image_comic_en__isnull=True).exclude(image_comic__isnull=True).update(
        image_comic_en=F('image_comic')
    )
    Action.objects.filter(audio_voice_en__isnull=True).exclude(audio_voice__isnull=True).update(
        audio_voice_en=F('audio_voice')
    )


def reverse_populate(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('scene', '0026_action_audio_voice_en_action_audio_voice_es_and_more'),
    ]

    operations = [
        migrations.RunPython(populate_translations, reverse_populate),
    ]
