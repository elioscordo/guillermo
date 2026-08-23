import django.db.models.deletion
import filer.fields.file
import filer.fields.image
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scene', '0027_populate_action_translations'),
        migrations.swappable_dependency(settings.FILER_IMAGE_MODEL),
        ('filer', '0017_image__transparent'),
    ]

    operations = [
        # prompt_comic translations
        migrations.AddField(
            model_name='historicalaction',
            name='prompt_comic_en',
            field=models.TextField(blank=True, null=True, verbose_name='prompt comic'),
        ),
        migrations.AddField(
            model_name='historicalaction',
            name='prompt_comic_it',
            field=models.TextField(blank=True, null=True, verbose_name='prompt comic'),
        ),
        migrations.AddField(
            model_name='historicalaction',
            name='prompt_comic_es',
            field=models.TextField(blank=True, null=True, verbose_name='prompt comic'),
        ),
        migrations.AddField(
            model_name='historicalaction',
            name='prompt_comic_pt',
            field=models.TextField(blank=True, null=True, verbose_name='prompt comic'),
        ),
        migrations.AddField(
            model_name='historicalaction',
            name='prompt_comic_fr',
            field=models.TextField(blank=True, null=True, verbose_name='prompt comic'),
        ),

        # prompt_voice translations
        migrations.AddField(
            model_name='historicalaction',
            name='prompt_voice_en',
            field=models.TextField(blank=True, null=True, verbose_name='prompt voice'),
        ),
        migrations.AddField(
            model_name='historicalaction',
            name='prompt_voice_it',
            field=models.TextField(blank=True, null=True, verbose_name='prompt voice'),
        ),
        migrations.AddField(
            model_name='historicalaction',
            name='prompt_voice_es',
            field=models.TextField(blank=True, null=True, verbose_name='prompt voice'),
        ),
        migrations.AddField(
            model_name='historicalaction',
            name='prompt_voice_pt',
            field=models.TextField(blank=True, null=True, verbose_name='prompt voice'),
        ),
        migrations.AddField(
            model_name='historicalaction',
            name='prompt_voice_fr',
            field=models.TextField(blank=True, null=True, verbose_name='prompt voice'),
        ),

        # image_comic translations
        migrations.AddField(
            model_name='historicalaction',
            name='image_comic_en',
            field=filer.fields.image.FilerImageField(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to=settings.FILER_IMAGE_MODEL, verbose_name='image comic'),
        ),
        migrations.AddField(
            model_name='historicalaction',
            name='image_comic_it',
            field=filer.fields.image.FilerImageField(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to=settings.FILER_IMAGE_MODEL, verbose_name='image comic'),
        ),
        migrations.AddField(
            model_name='historicalaction',
            name='image_comic_es',
            field=filer.fields.image.FilerImageField(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to=settings.FILER_IMAGE_MODEL, verbose_name='image comic'),
        ),
        migrations.AddField(
            model_name='historicalaction',
            name='image_comic_pt',
            field=filer.fields.image.FilerImageField(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to=settings.FILER_IMAGE_MODEL, verbose_name='image comic'),
        ),
        migrations.AddField(
            model_name='historicalaction',
            name='image_comic_fr',
            field=filer.fields.image.FilerImageField(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to=settings.FILER_IMAGE_MODEL, verbose_name='image comic'),
        ),

        # audio_voice translations
        migrations.AddField(
            model_name='historicalaction',
            name='audio_voice_en',
            field=filer.fields.file.FilerFileField(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='filer.file', verbose_name='audio voice'),
        ),
        migrations.AddField(
            model_name='historicalaction',
            name='audio_voice_it',
            field=filer.fields.file.FilerFileField(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='filer.file', verbose_name='audio voice'),
        ),
        migrations.AddField(
            model_name='historicalaction',
            name='audio_voice_es',
            field=filer.fields.file.FilerFileField(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='filer.file', verbose_name='audio voice'),
        ),
        migrations.AddField(
            model_name='historicalaction',
            name='audio_voice_pt',
            field=filer.fields.file.FilerFileField(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='filer.file', verbose_name='audio voice'),
        ),
        migrations.AddField(
            model_name='historicalaction',
            name='audio_voice_fr',
            field=filer.fields.file.FilerFileField(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='filer.file', verbose_name='audio voice'),
        ),
    ]
