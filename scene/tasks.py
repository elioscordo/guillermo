from task.models import Task
from agent.models import GetContentsMixin
from moviepy import ImageClip, VideoFileClip, AudioFileClip, concatenate_videoclips
from moviepy.video.fx import Resize
import random
from django.utils.text import slugify
import os 
from django.conf import settings
from filer.models.imagemodels import Image as FilerImage

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
                    duration = audio_clip.duration
                    clip = ImageClip(render_item.image.path, duration=duration)
                    
                    # Professional subtle zoom-in effect (Ken Burns)
                    clip = clip.with_effects([Resize(lambda t: 1.0 + 0.1 * (t / duration))])
                    clip = clip.with_audio(audio_clip)
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
