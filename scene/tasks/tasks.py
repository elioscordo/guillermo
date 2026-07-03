from task.models import Task
from agent.models import GetContentsMixin
from django.utils.text import slugify
from django.conf import settings
from django.core.files.base import ContentFile


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
