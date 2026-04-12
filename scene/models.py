from django.db import models
from django.conf import settings
from agent.models import Agent
from filer.fields.image import FilerImageField, FilerFileField
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from google.genai import types
from agent.models import GetContentsMixin
from task.models import TaskHolder, Task

from django.utils.safestring import mark_safe
from PIL import Image


class Style(models.Model, GetContentsMixin):
    prompt = models.TextField(null=True, blank=True)
    name = models.CharField(max_length=100, default="")
    
    def __str__(self):
        return "{}".format(self.name)
    
    def context_text(self, generate_self=True, preset=None):
        if preset == self.PRESET_REFINE:
            return self.prompt_refine
        return self.prompt

class Prop(models.Model, GetContentsMixin, TaskHolder):
    name = models.CharField(max_length=100, default="")
    image = FilerImageField(null=True, blank=True, on_delete=models.SET_NULL, related_name='props')
    prompt= models.TextField(null=True, blank=True)
    prompt_refine = models.TextField(null=True, blank=True)
    story = models.ForeignKey('Story', related_name='props', null=True, blank=True, on_delete=models.CASCADE)

    # trick to save and execute tasks
    TASK_TYPE_CHOICES = settings.TASK_TYPE_CHOICES
    exec_on_save = models.SlugField(choices=settings.TASK_TYPE_CHOICES, null=True, blank=True)

    class Meta:
        verbose_name = 'Element'
        verbose_name_plural = 'Elements'

    def save(self, *args, **kwargs):
        print("Saving background, checking for exec_on_save task: {}".format(self.exec_on_save))
        exec_on_save = getattr(self, 'exec_on_save', None)
        if exec_on_save is not None:
            self.exec_on_save = None
        super().save(*args, **kwargs)
        if exec_on_save is not None: 
            Task.createTaskIfQueueEnabled(
                    subject=self,
                    task_type=exec_on_save
                )
   
    def __str__(self):
        return "{}".format(self.name)

    def context_text(self, generate_self=True, preset=None):
        if preset == self.PRESET_REFINE:
            return self.prompt_refine
        if generate_self:
            return self.prompt
        return f"Object or Prop referenced as: {self.name}:"
    
    def get_contents(self, generate_self=True, preset=None):
        parts = super().get_contents(generate_self=generate_self, preset=preset)
        if self.story and self.story.style and generate_self:
            parts.extend(self.story.style.get_contents())
        return parts

class Character(models.Model, GetContentsMixin, TaskHolder):
    name = models.CharField(max_length=100, default="")
    image = FilerImageField(null=True, blank=True, on_delete=models.SET_NULL, related_name='characters')
    prompt= models.TextField(null=True, blank=True)
    prompt_refine = models.TextField(null=True, blank=True)
    story = models.ForeignKey('Story', related_name='characters', null=True, blank=True, on_delete=models.CASCADE)

    TASK_TYPE_CHOICES = settings.TASK_TYPE_CHOICES
    exec_on_save = models.SlugField(choices=settings.TASK_TYPE_CHOICES, null=True, blank=True)

    def save(self, *args, **kwargs):
        exec_on_save = getattr(self, 'exec_on_save', None)
        if exec_on_save is not None:
            self.exec_on_save = None
        super().save(*args, **kwargs)
        if exec_on_save is not None: 
            Task.createTaskIfQueueEnabled(
                    subject=self,
                    task_type=exec_on_save
                )
   
    def __str__(self):
        return "{}".format(self.name)

    def context_text(self, generate_self=True, preset=None):
        if preset == self.PRESET_REFINE:
            return self.prompt_refine
        if generate_self:
            return self.prompt
        return f"Character: {self.name}:"

    def get_contents(self, generate_self=True, preset=None):
        parts = super().get_contents(generate_self=generate_self, preset=preset)
        if self.story and self.story.style and generate_self:
            parts.extend(self.story.style.get_contents(generate_self=False))
        return  parts # reverse to have the character prompt last so it is more important

    class Meta:
        verbose_name = 'Actor'
        verbose_name_plural = 'Actors'


class Background(models.Model, GetContentsMixin, TaskHolder):
    name = models.CharField(max_length=100, default="")
    prompt= models.TextField(null=True, blank=True)
    image = FilerImageField(null=True, blank=True, on_delete=models.SET_NULL, related_name='backgrounds')
    prompt_refine = models.TextField(null=True, blank=True)
    image_refine = FilerImageField(null=True, blank=True, on_delete=models.SET_NULL, related_name='background_refine')
    story = models.ForeignKey('Story', related_name='backgrounds', null=True, blank=True, on_delete=models.CASCADE)

    TASK_TYPE_CHOICES = settings.TASK_TYPE_CHOICES
    exec_on_save = models.SlugField(choices=settings.TASK_TYPE_CHOICES, null=True, blank=True)


    def __str__(self):
        return "{}".format(self.name)

    def save(self, *args, **kwargs):
        print("Saving background, checking for exec_on_save task: {}".format(self.exec_on_save))
        exec_on_save = getattr(self, 'exec_on_save', None)
        if exec_on_save is not None:
            self.exec_on_save = None
        super().save(*args, **kwargs)
        if exec_on_save is not None: 
            Task.createTaskIfQueueEnabled(
                    subject=self,
                    task_type=exec_on_save
                )

    def context_text(self, generate_self=True, preset=None):
        if preset == self.PRESET_REFINE:
            return self.prompt_refine
        if generate_self:
            return self.prompt
        return self.name

    def get_contents(self, generate_self=True, preset=None):
        parts = super().get_contents(generate_self=generate_self, preset=preset)
        if self.story and self.story.style and generate_self and not preset == self.PRESET_REFINE:
            parts.extend(self.story.style.get_contents())
        return parts

    class Meta:
        verbose_name = 'Location'
        verbose_name_plural = 'Locations'


class Scene(models.Model):
    name = models.CharField(max_length=200, default="Scene")
    prompt = models.TextField(null=True, blank=True)
    order = models.PositiveIntegerField(default=0, db_index=True)
    story = models.ForeignKey('Story', related_name='scenes', null=True, blank=True, on_delete=models.CASCADE)

    def __str__(self):
        return "{}".format(self.name)

    def get_contents(self, generate_self=True):
        contents = []
        if self.story and self.story.style:
            contents.extend(self.story.style.get_contents(generate_self=False))
        return contents

    class Meta:
        ordering = ['order']


class Story(models.Model, GetContentsMixin, TaskHolder):
    name = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=0, db_index=True)
    style = models.ForeignKey(Style, related_name='stories', null=True, blank=True, on_delete=models.CASCADE)

    def __str__(self):
        return "{}".format(self.name)




class StoryProfile(models.Model, GetContentsMixin, TaskHolder):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name='profile', on_delete=models.CASCADE)
    story = models.ForeignKey(Story, related_name='story_profiles', on_delete=models.SET_NULL, null=True, blank=True)
    scene = models.ForeignKey(Scene, related_name='story_profiles', on_delete=models.SET_NULL, null=True, blank=True)
    enable_filters = models.BooleanField(default=False)

    def __str__(self):
        return "{}".format(self.id)


class Action(models.Model, GetContentsMixin, TaskHolder):
    name = models.CharField(max_length=200, default="Action")
    scene = models.ForeignKey(Scene, related_name='actions', on_delete=models.CASCADE)
    prompt = models.TextField(null=True, blank=True)
    order = models.PositiveIntegerField(default=0, db_index=True)
    image = FilerImageField(null=True, blank=True, on_delete=models.SET_NULL, related_name='panel')
    background = models.ForeignKey(Background, related_name='actions', on_delete=models.SET_NULL, null=True, blank=True)
    actor = models.ForeignKey(Character, related_name='actions', on_delete=models.SET_NULL, null=True, blank=True)
    props = models.ManyToManyField(Prop, related_name='actions', blank=True)
    extras = models.ManyToManyField(Character, related_name='actions_extras', blank=True)
    consistent_with = models.ForeignKey('self', related_name='consistent_actions', on_delete=models.SET_NULL, null=True, blank=True)
    prompt_refine = models.TextField(null=True, blank=True)
    image_refine = FilerImageField(null=True, blank=True, on_delete=models.SET_NULL, related_name='action_refine')
    # video
    image_first = FilerImageField(null=True, blank=True, on_delete=models.SET_NULL, related_name='actions_first')
    image_last = FilerImageField(null=True, blank=True, on_delete=models.SET_NULL, related_name='actions_last')
    video = FilerFileField(null=True, blank=True, on_delete=models.SET_NULL, related_name='actions_video')
    prompt_video = models.TextField(null=True, blank=True)

    TASK_TYPE_CHOICES = settings.TASK_TYPE_CHOICES
    exec_on_save = models.SlugField(choices=settings.TASK_TYPE_CHOICES, null=True, blank=True)

    prompt_comic = models.TextField(null=True, blank=True)
    image_comic = FilerImageField(null=True, blank=True, on_delete=models.SET_NULL, related_name='actions_comic')

    voice = FilerFileField(null=True, blank=True, on_delete=models.SET_NULL, related_name='actions_audio')
    prompt_voice = models.TextField(null=True, blank=True)

    def __str__(self):
        return "{}_{}".format(self.scene.name, self.id)
    
    
    class Meta:
        ordering = ['-order', 'name']

    def elements(self):
        props = []
        extras = []
        main_actor = self.actor.name if self.actor else "None"
        background = self.background.name if self.background else "None"
        if self.props:
            props.extend([prop.name for prop in self.props.all()])
        if self.extras:
            extras.extend([extra.name for extra in self.extras.all()])
        output =  f"Main Actor: <b>{main_actor}</b><br/> Background: <b>{background}</b><br/> Props: <b>{', '.join(props)}</b><br/> Extras: <b>{', '.join(extras)}</b><br/>"
        return mark_safe(output)
    
    def get_thumbnail(self, preset=None):
        return Image.open(self.image.path)

    def generate_comic(self, user=None):
        image_agent = Agent.objects.filter(output_type=Agent.OUTPUT_TYPE_IMAGE).first()
        out = image_agent.generate(self, preset=self.PRESET_COMIC, user=user)
        return out
    
    def get_contents(self, generate_self=True, preset=None):
        if preset == self.PRESET_VIDEO:
            contents = {}
            contents['prompt'] = self.prompt_video
            contents['image'] = types.Image.from_file(location=self.image.path)
        elif preset == self.PRESET_VIDEO_FIRST_LAST:
            contents = {}
            contents['prompt'] = self.prompt_video
            contents['image_first'] = types.Image.from_file(location=self.image_first.path) if self.image_first else None
            contents['image_last'] = types.Image.from_file(location=self.image_last.path) if self.image_last else None
        elif preset == self.PRESET_VOICE:
            contents = {}
            contents['prompt'] = self.prompt_voice
        else:
            # preset refine is handled in the mixin
            contents = super().get_contents(generate_self=generate_self, preset=preset)
            if preset != self.PRESET_COMIC:
                if self.consistent_with:
                    contents.extend(["Maximise consistency, preserve character features and objects to the following image", self.consistent_with.get_thumbnail()])
                if self.actor:
                    contents.extend(self.actor.get_contents(generate_self=False))
                if self.extras:
                    for extra in self.extras.all():
                        contents.extend(extra.get_contents(generate_self=False))
                if self.props:
                    for prop in self.props.all():
                        contents.extend(prop.get_contents(generate_self=False))
                if self.background:
                    contents.extend(self.background.get_contents(generate_self=False))
                if self.scene:
                    contents.extend(self.scene.get_contents(generate_self=False))
        return contents
    
    def context_text(self, generate_self=True, preset=None):
        if preset == self.PRESET_COMIC:
            return self.prompt_comic
        if preset == self.PRESET_REFINE:
            return self.prompt_refine
        if not generate_self:
            return self.name
        return self.prompt
    
    def save(self, *args, **kwargs):
        print("Saving background, checking for exec_on_save task: {}".format(self.exec_on_save))
        exec_on_save = getattr(self, 'exec_on_save', None)
        if exec_on_save is not None:
            self.exec_on_save = None
        super().save(*args, **kwargs)
        if exec_on_save is not None: 
            Task.createTaskIfQueueEnabled(
                    subject=self,
                    task_type=exec_on_save
                )

class VideoAction(Action):
    class Meta:
        proxy = True

class ComicAction(Action):
    class Meta:
        proxy = True

class VoiceAction(Action):
    class Meta:
        proxy = True

class SceneVideo(models.Model, TaskHolder):
    name = models.CharField(max_length=200, default="")
    scene = models.ForeignKey(Scene, related_name='scene_video', on_delete=models.CASCADE)
    video = FilerFileField(null=True, blank=True, on_delete=models.SET_NULL, related_name='scene_video_video')

    def __str__(self):
        return "{}".format(self.name)

    @classmethod
    def get_from_scene(cls, scene):
        video = cls.objects.filter(scene=scene).first()
        if not video:
            video = cls.objects.create(name=scene.name, scene=scene)
        return video
    
    class Meta:
        verbose_name = 'Video'
        verbose_name_plural = 'Videos'


class VideoItem(models.Model, TaskHolder):
    DEFAULT_IMAGE_DURATION = 8
    name = models.CharField(max_length=200, default="Video")
    image = FilerImageField(null=True, blank=True, on_delete=models.SET_NULL, related_name='video_item')
    video = FilerFileField(null=True, blank=True, on_delete=models.SET_NULL, related_name='video_item_video')
    order = models.PositiveIntegerField(default=0, db_index=True)
    config = models.JSONField(null=True, blank=True)
    scene_video = models.ForeignKey(SceneVideo, related_name='video_items',null=True, blank=True, on_delete=models.CASCADE)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return "{}".format(self.name)
    
    class Meta:
        verbose_name = 'Video Shot'
        verbose_name_plural = 'Video Shots'

    @property
    def duration(self):
        out = self.DEFAULT_IMAGE_DURATION
        if self.config and 'duration' in self.config: 
            out = self.config['duration']
        return out