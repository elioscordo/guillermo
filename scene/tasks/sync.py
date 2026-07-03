from scene.resources import (
    StoryResource, CharacterResource, BackgroundResource, 
    PropResource, SceneResource, ActionResource
)
from scene.models import Action
from django.utils.text import slugify
import io
import zipfile
import tempfile
from django.core.files.base import ContentFile


class TaskSyncExport:
    def __init__(self, task):
        self.task = task

    def process(self):
        sync_item = self.task.subject
        sync = sync_item.sync
        story = sync.story
        from filer.models.filemodels import File as FilerFile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # 1. Export Data as CSVs
            zip_file.writestr('data/story.csv', StoryResource().export(story.__class__.objects.filter(id=story.id)).csv)
            zip_file.writestr('data/characters.csv', CharacterResource().export(story.characters.all()).csv)
            zip_file.writestr('data/backgrounds.csv', BackgroundResource().export(story.backgrounds.all()).csv)
            zip_file.writestr('data/props.csv', PropResource().export(story.props.all()).csv)
            
            scenes = story.scenes.all()
            zip_file.writestr('data/scenes.csv', SceneResource().export(scenes).csv)
            
            actions = Action.objects.filter(scene__in=scenes)
            zip_file.writestr('data/actions.csv', ActionResource().export(actions).csv)

            # 2. Helper to add media files
            def add_filer_file(filer_file, folder):
                if filer_file and hasattr(filer_file, 'file') and filer_file.file:
                    try:
                        file_path = filer_file.file.path
                        arcname = os.path.join(folder, os.path.basename(file_path))
                        if arcname not in zip_file.namelist():
                            zip_file.write(file_path, arcname)
                    except Exception:
                        pass

            for char in story.characters.all():
                add_filer_file(char.image, "media/characters")
            for bg in story.backgrounds.all():
                add_filer_file(bg.image, "media/backgrounds")
                add_filer_file(bg.image_refine, "media/backgrounds")
            for prop in story.props.all():
                add_filer_file(prop.image, "media/props")
            for action in actions:
                add_filer_file(action.image, "media/actions")
                add_filer_file(action.image_comic, "media/actions")
                add_filer_file(action.video, "media/videos")
                add_filer_file(action.audio_voice, "media/audio")

        buffer.seek(0)
        filename = f"export_{slugify(story.name)}_{sync_item.id}.zip"
        
        out_file = FilerFile.objects.create(
            original_filename=filename,
            file=ContentFile(buffer.read(), name=filename),
            name=filename
        )
        sync_item.zip_file = out_file
        sync_item.save()
        
        sync.last_file_out = out_file
        sync.save()

class TaskSyncImport:
    def __init__(self, task):
        self.task = task

    def process(self):
        sync_item = self.task.subject
        sync = sync_item.sync
        story = sync.story
        
        if not sync_item.zip_file:
            self.task.log("Missing zip file for import")
            return

        # Update sync model to track the last imported file
        sync.last_file_in = sync_item.zip_file
        sync.save()
        
        # Unzip to temp folder - placeholder for robust resource import logic
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                with zipfile.ZipFile(sync_item.zip_file.file.path, 'r') as zf:
                    zf.extractall(temp_dir)
                self.task.log(f"Import extracted to {temp_dir}. Deep resource sync from zip requires resource adjustment.")
            except Exception as e:
                self.task.log(f"Extraction failed: {str(e)}")
