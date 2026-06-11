from task.models import Task
from agent.models import GetContentsMixin
from moviepy import ImageClip, VideoFileClip, AudioFileClip, concatenate_videoclips
from moviepy.video.fx import Resize
import random
from django.utils.text import slugify
import os 
from django.conf import settings
import io
import zipfile
import tempfile
from django.core.files.base import ContentFile
from .resources import (
    StoryResource, CharacterResource, BackgroundResource, 
    PropResource, SceneResource, ActionResource
)

class TaskGenerateImage:
    
    def __init__(self, task):
        self.task = task

    def process(self):
        self.task.set_status(Task.TASK_STATUS_STARTED)
        item = self.task.subject
        item.generate_image(user=self.task.owner)
        self.task.set_status(Task.TASK_STATUS_SUCCESS)


class TaskRefineImage:
    
    def __init__(self, task):
        self.task = task
        
    def process(self):
        item = self.task.subject
        old_image = item.image.url
        item.refine_image(user=self.task.owner)
        image = item.image.url
        print(f"Refined image for item ID {item.id} from {old_image} to {image}")

class TaskGenerateVideo:
    def __init__(self, task):
        self.task = task
    def process(self):
        item = self.task.subject
        item.generate_video(GetContentsMixin.PRESET_VIDEO, user=self.task.owner)

class TaskGenerateVoice:
    def __init__(self, task):
        self.task = task
    def process(self):
        item = self.task.subject
        item.generate_voice(GetContentsMixin.PRESET_VOICE, user=self.task.owner)

class TaskGenerateVideoFirstLast:
    def __init__(self, task):
        self.task = task
        
    def process(self):
        item = self.task.subject
        item.generate_video(GetContentsMixin.PRESET_VIDEO_FIRST_LAST, user=self.task.owner)

class TaskGenerateComic:
    def __init__(self, task):
        self.task = task
    def process(self):
        item = self.task.subject
        item.image_comic = item.generate_comic(user=self.task.owner)
        item.save()

class TaskExtractScene:
    def __init__(self, task):
        self.task = task
    def process(self):
        item = self.task.subject
        log = item.generate_scene(user=self.task.owner)
        self.task.log(log)

class TaskGenerateText:
    def __init__(self, task):
        self.task = task
    def process(self):
        item = self.task.subject
        agent = self.task.thr
        if hasattr(item, 'generate_text'):
            item.generate_text(agent=agent, user=self.task.owner)
        elif self.task.payload and 'target_field' in self.task.payload:
            out = agent.generate(self, preset=GetContentsMixin.PRESET_TEXT, user=self.task.owner, target_field=self.task.payload['target_field'])
            setattr(self, self.task.payload['target_field'], out)
            self.save()
        else:
            raise ValueError("TaskGenerateText requires 'target_field' in task payload or custom generate text method on the model.")

class VideoRender:
    def __init__(self, task):
        self.task = task
    def process(self):
        item = self.task.subject

        from filer.models.imagemodels import Image as FilerImage
        clips = []
        first = None

        if item.render_type == item.RENDER_TYPE_GRAPHIC_NOVEL:
            return

        for render_item in item.render_items.all():
            clip = None
            if item.render_type == item.RENDER_TYPE_FILM:
                if render_item.video:
                    clip = VideoFileClip(render_item.video.path, audio=True)
                else:
                    self.task.log(f"Render item {render_item.order} skipped: Missing video file for Film render.")

            elif item.render_type == item.RENDER_TYPE_ANIMATIC:
                if render_item.image and render_item.audio:
                    audio_clip = AudioFileClip(render_item.audio.path)

                    # Get margins from 'params' field (space separated "start_ms end_ms")
                    # Fallback to config or settings if params is empty
                    default_margin = (render_item.config or {}).get('audio_margin', getattr(settings, 'DEFAULT_AUDIO_MARGIN', 0.5))
                    start_ms, end_ms = default_margin, default_margin
                    
                    if render_item.params:
                        try:
                            parts = render_item.params.split()
                            if len(parts) >= 1:
                                # Convention: 10 = 1s, 3 = 0.3s (multiply by 100 for ms)
                                start_ms = float(parts[0]) * 100
                                end_ms = start_ms 
                            if len(parts) >= 2:
                                end_ms = float(parts[1]) * 100
                        except (ValueError, IndexError):
                            pass

                    start_sec, end_sec = start_ms / 1000.0, end_ms / 1000.0

                    # Total duration = start_margin + audio + end_margin
                    duration = audio_clip.duration + start_sec + end_sec
                    clip = ImageClip(render_item.image.path, duration=duration)
                    
                    # Professional subtle zoom-in effect (Ken Burns)
                    clip = clip.with_effects([Resize(lambda t: 1.0 + 0.1 * (t / duration))])
                    clip = clip.with_audio(audio_clip.with_start(start_sec))
                else:
                    self.task.log(f"Render item {render_item.order} skipped: Animatic requires both image and audio.")

            if clip:
                if first:
                    clip = clip.with_effects([Resize(width=first.w)])
                if not first:
                    first = clip
                clips.append(clip)

        if clips:
            final_clip = concatenate_videoclips(clips, method="compose")
            name = f"video_{slugify(item.__class__.__name__)}_{slugify(item.name)}_{random.randint(1000,9999)}.mp4"
            filepath_relative = f"exported_videos/{name}"
            filepath_abs = os.path.join( settings.MEDIA_ROOT, filepath_relative)

            final_clip.write_videofile(filepath_abs, fps=24, codec='libx264',
                     audio_codec='aac', temp_audiofile='temp-audio.m4a', remove_temp=True)
            out = FilerImage.objects.create(
                original_filename=name,
                file=filepath_relative,
                name=name
            )
            item.video = out
            item.save()

class TaskGenerateScene:
    """
    Extract scene from text and generate a scene object with associated media.
    """
    def __init__(self, task):
        self.task = task
    def process(self):
        item = self.task.subject
        item.generate_scene(user=self.task.owner)
        item.save()

class TaskGenerateSceneElements:
    """
    Iterates through all actions of a scene and triggers image generation 
    for any missing background (location), character (cast/actor), or prop,
    as well as voice generation for missing character voice samples.
    """
    def __init__(self, task):
        self.task = task

    def process(self):
        scene = self.task.subject
        elements = set()
        voices = set()

        for action in scene.actions.all():
            if action.background: elements.add(action.background)
            if action.actor: 
                elements.add(action.actor)
                if action.actor.voice: voices.add(action.actor.voice)
            for char in action.cast.all(): 
                elements.add(char)
                if char.voice: voices.add(char.voice)
            for prop in action.props.all(): elements.add(prop)
            if action.voice: voices.add(action.voice)

        for element in elements:
            if not element.image:
                self.task.log(f"Queueing image generation for {element.name} ({element.__class__.__name__})")
                Task.createTaskIfQueueEnabled(
                    subject=element,
                    task_type=settings.TASK_TYPE_GENERATE_IMAGE,
                    thr=scene,
                    owner=self.task.owner
                )

        for voice in voices:
            if not voice.audio_voice:
                self.task.log(f"Queueing voice generation for {voice.name}")
                Task.createTaskIfQueueEnabled(
                    subject=voice,
                    task_type=settings.TASK_TYPE_GENERATE_VOICE,
                    thr=scene,
                    owner=self.task.owner
                )

class TaskGenerateSceneActions:
    """
    Generates images for all actions in a scene.
    Ensures that if an action's element is missing an image, 
    the element's generation task is queued immediately before the action's task.
    """
    def __init__(self, task):
        self.task = task

    def process(self):
        scene = self.task.subject
        element_tasks_buffer = {}  # key: (model_name, id)

        for action in scene.actions.all().order_by('order'):
            # Elements required for this action
            elements = []
            if action.background: elements.append(action.background)
            if action.actor: elements.append(action.actor)
            elements.extend(list(action.cast.all()))
            elements.extend(list(action.props.all()))

            # Ensure action-specific voice is generated if dialogue text exists
            if action.voice and action.text and not action.audio_voice:
                self.task.log(f"Queuing dialogue voice generation for action: {action.get_name()}")
                Task.createTaskIfQueueEnabled(
                    subject=action,
                    task_type=settings.TASK_TYPE_GENERATE_VOICE,
                    thr=scene,
                    owner=self.task.owner
                )

            # Identify tasks for missing element images
            action_dependencies = []
            for element in elements:
                if not element.image:
                    key = (element._meta.model_name, element.id)
                    if key not in element_tasks_buffer:
                        e_task = Task.createTaskIfQueueEnabled(
                            subject=element,
                            task_type=settings.TASK_TYPE_GENERATE_IMAGE,
                            thr=scene,
                            owner=self.task.owner,
                            process=False
                        )
                        if e_task:
                            element_tasks_buffer[key] = e_task
                    
                    if key in element_tasks_buffer:
                        action_dependencies.append(element_tasks_buffer[key])

            # Queue action image generation
            if not action.image:
                action_task = Task.createTaskIfQueueEnabled(
                    subject=action,
                    task_type=settings.TASK_TYPE_GENERATE_IMAGE,
                    thr=scene,
                    owner=self.task.owner,
                    process=False
                )
                if action_task:
                    self.task.log(f"Queuing image generation for action: {action.get_name()}")
                    for dep_task in action_dependencies:
                        dep_task.next_tasks.add(action_task)
                    action_task.process()

        # Trigger processing for all element tasks in the buffer
        for e_task in element_tasks_buffer.values():
            e_task.process()

class TaskSyncExport:
    def __init__(self, task):
        self.task = task

    def process(self):
        from .models import Action
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
