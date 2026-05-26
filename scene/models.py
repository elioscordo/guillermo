from django.db import models
from django.conf import settings
from agent.models import Agent, Prompt, Voice
from filer.fields.image import FilerImageField, FilerFileField
from agent.models import GetContentsMixin
from scene.mixins import EmailSenderMixin, UserCreatorMixin
from task.models import TaskHolder, Task

from django.utils.safestring import mark_safe
from PIL import Image

def dashboard_callback(request, context):
    stories = []
    if request.user.is_authenticated:
            stories =  Story.objects.filter(authors__user=request.user).distinct()
    context.update({'stories': stories})
    return context

class Theme(models.Model):
    name = models.CharField(max_length=100, default='New Game')
    prompt = models.TextField(null=True, blank=True)
    
    def __str__(self):
        return "{}".format(self.name)


class Style(models.Model, GetContentsMixin):
    prompt = models.TextField(null=True, blank=True)
    name = models.CharField(max_length=100, default="")
    global_default = models.BooleanField(default=False)
    
    def __str__(self):
        return "{}".format(self.name)
    
    def context_text(self, generate_self=True, preset=None):
        if preset == self.PRESET_REFINE:
            return self.prompt_refine
        return self.prompt



class Author(models.Model, UserCreatorMixin):
    story = models.ForeignKey('scene.Story', related_name='authors', on_delete=models.CASCADE, null=True, blank=True)
    order = models.IntegerField(default=0)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='authors', on_delete=models.CASCADE, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.email and not self.user:
            raise ValueError("Either email or user must be provided.")
        if self.email and self.user is None:
            user = self.create_user(self.story, self.email)
            self.user = user
        super().save(*args, **kwargs)
           

    def __str__(self):
        return "{}".format(self.user.username if self.user else self.email)

    def username(self):
        return self.user.username if self.user else self.email

class Story(models.Model, GetContentsMixin, TaskHolder):
    name = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=0, db_index=True)
    style = models.ForeignKey(Style, related_name='stories', null=True, blank=True, on_delete=models.CASCADE)
    theme = models.ForeignKey('Theme', on_delete=models.CASCADE, null=True, blank=True)
    group = models.ForeignKey('scene.StoryGroup', help_text="Auto create authors from this group, it happens only when the script is saved for the first time",  on_delete=models.CASCADE, null=True, blank=True, related_name='stories')

    RENDER_TYPE_FILM = 'film'
    RENDER_TYPE_GRAPHIC_NOVEL = 'graphic_novel'
    RENDER_TYPE_ANIMATIC = 'animatic'

    RENDER_TYPE_CHOICES = [
        (RENDER_TYPE_FILM, 'Film'),
        (RENDER_TYPE_GRAPHIC_NOVEL, 'Graphic Novel'),
        (RENDER_TYPE_ANIMATIC, 'Animatic'),
    ]

    render_type = models.CharField(
        max_length=50,
        choices=RENDER_TYPE_CHOICES,
        default=getattr(settings, 'DEFAULT_RENDER_TYPE', RENDER_TYPE_ANIMATIC),
        help_text="The default render format for this story."
    )
    
    def __str__(self):
        return "{}".format(self.name)

    def import_group_members(self):
        if self.group is not None:
            for member in self.group.users.all():
                if not Author.objects.filter(story=self, user=member).exists():
                    Author.objects.create(story=self, user=member)

    def add_author(self, user):
        out = False
        if not Author.objects.filter(story=self, user=user).exists():
            Author.objects.create(story=self, user=user)
            out = True
        return out

    def save(self, *args, **kwargs):
        if not self.style:
            default_style = Style.objects.filter(global_default=True).first()
            if default_style:
                self.style = default_style
                
        do_import = not self.id and self.group is not None
        super().save(*args, **kwargs)
        if do_import:
            self.import_group_members()




class Nudge(models.Model, EmailSenderMixin):
    email_template = 'email/nudge.html'

    sender = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='sent_nudges', on_delete=models.CASCADE, null=True, blank=True)
    receiver = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='received_nudges', on_delete=models.CASCADE, null=True, blank=True)
    story = models.ForeignKey('scene.Story', related_name='nudges', on_delete=models.CASCADE, null=True, blank=True)
    message = models.TextField(null=True, blank=True, help_text="Optional message to include in the nudge email.")
    created_at = models.DateTimeField(auto_now_add=True)
    read = models.BooleanField(default=False)

    def __str__(self):
        return "{}".format(self.sender.username)

    def mark_as_read(self):
        self.read = True
        self.save() 
   
    def save(self, *args, **kwargs):
        if self.sender == self.receiver:
            raise ValueError("Sender and receiver cannot be the same user.")
        
        if not self.id:
            author = Author.objects.filter(story=self.story, user=self.receiver).first()
            cta_url = ""
            if author:
                cta_url = settings.SITE_URL + f'/admin/brainstorm/scene/add?story={self.story.id}&author={author.id}&type={self.story.contribution_type()}'
        super().save(*args, **kwargs)
        self.send_email(
            subject=f"Nudge on the story: {self.story.name}. {self.sender.username} nudged you!",
            context={
                'item': self,
                'cta': cta_url
            },
            recipient_list=[self.receiver.email]
        )


class Prop(models.Model, GetContentsMixin, TaskHolder):
    name = models.CharField(max_length=100, default="")
    image = FilerImageField(null=True, blank=True, on_delete=models.SET_NULL, related_name='props')
    prompt= models.TextField(null=True, blank=True)
    prompt_refine = models.TextField(null=True, blank=True)
    story = models.ForeignKey('Story', related_name='props', null=True, blank=True, on_delete=models.CASCADE)

    # trick to save and execute tasks
    TASK_TYPE_CHOICES = settings.TASK_TYPE_CHOICES
    action = models.SlugField(choices=settings.TASK_TYPE_CHOICES, null=True, blank=True)

    class Meta:
        verbose_name = 'Element'
        verbose_name_plural = 'Elements'

    def save(self, *args, **kwargs):
        print("Saving background, checking for action task: {}".format(self.action))
        action = getattr(self, 'action', None)
        if action is not None:
            self.action = None
        super().save(*args, **kwargs)
        if action is not None: 
            Task.createTaskIfQueueEnabled(
                    subject=self,
                    task_type=action
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
            parts.extend(Prompt.prompt_for_model(self))
        return parts

class Character(models.Model, GetContentsMixin, TaskHolder):
    name = models.CharField(max_length=100, default="")
    image = FilerImageField(null=True, blank=True, on_delete=models.SET_NULL, related_name='characters')
    prompt= models.TextField(null=True, blank=True)
    prompt_refine = models.TextField(null=True, blank=True)
    story = models.ForeignKey('Story', related_name='characters', null=True, blank=True, on_delete=models.CASCADE)
    voice = models.ForeignKey(Voice, related_name='characters', on_delete=models.SET_NULL, null=True, blank=True) 
    TASK_TYPE_CHOICES = settings.TASK_TYPE_CHOICES
    action = models.SlugField(choices=settings.TASK_TYPE_CHOICES, null=True, blank=True)

    def save(self, *args, **kwargs):
        action = getattr(self, 'action', None)
        if action is not None:
            self.action = None
        super().save(*args, **kwargs)
        if action is not None: 
            Task.createTaskIfQueueEnabled(
                    subject=self,
                    task_type=action
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
        parts.extend(Prompt.prompt_for_model(self))
        if self.story and self.story.style and generate_self:
            parts.extend(self.story.style.get_contents(generate_self=False))
        return  parts # reverse to have the character prompt last so it is more important

    class Meta:
        verbose_name = 'Character'
        verbose_name_plural = 'Characters'


class Background(models.Model, GetContentsMixin, TaskHolder):
    name = models.CharField(max_length=100, default="")
    prompt= models.TextField(null=True, blank=True)
    image = FilerImageField(null=True, blank=True, on_delete=models.SET_NULL, related_name='backgrounds')
    prompt_refine = models.TextField(null=True, blank=True)
    image_refine = FilerImageField(null=True, blank=True, on_delete=models.SET_NULL, related_name='background_refine')
    story = models.ForeignKey('Story', related_name='backgrounds', null=True, blank=True, on_delete=models.CASCADE)

    TASK_TYPE_CHOICES = settings.TASK_TYPE_CHOICES
    action = models.SlugField(choices=settings.TASK_TYPE_CHOICES, null=True, blank=True)


    def __str__(self):
        return "{}".format(self.name)

    def save(self, *args, **kwargs):
        print("Saving background, checking for action task: {}".format(self.action))
        action = getattr(self, 'action', None)
        if action is not None:
            self.action = None
        super().save(*args, **kwargs)
        if action is not None: 
            Task.createTaskIfQueueEnabled(
                    subject=self,
                    task_type=action
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
            parts.extend(Prompt.prompt_for_model(self))
        return parts

    class Meta:
        verbose_name = 'Location'
        verbose_name_plural = 'Locations'


class Scene(models.Model, TaskHolder, GetContentsMixin):
    name = models.CharField(max_length=200, null=True, blank=True)
    prompt = models.TextField(null=True, blank=True, default="#Location\n#Cast\n#Props\n#Actions\n")
    prompt_refine = models.TextField(null=True, blank=True)
    order = models.PositiveIntegerField(default=0, db_index=True)
    story = models.ForeignKey('Story', related_name='scenes', null=True, blank=True, on_delete=models.CASCADE)
    author = models.ForeignKey('Author', related_name='scenes', on_delete=models.CASCADE, null=True, blank=True)
    action = models.SlugField(choices=settings.TASK_TYPE_CHOICES, null=True, blank=True)

    def __str__(self):
        return "{}".format(self.name if self.name else f"Scene{self.id} of {self.story}")
    
    def get_contents(self, generate_self=True):
        contents = []
        if self.story and self.story.style:
            contents.extend(self.story.style.get_contents(generate_self=False))
            contents.extend(Prompt.prompt_for_model(self))
        return contents

    def get_contents(self, generate_self=True, preset=None):
        parts = []
        if not generate_self:
            parts.extend(self.story.style.get_contents(generate_self=False))
        if preset == self.PRESET_REFINE_PROMPT and generate_self:
            parts = [self.prompt_refine]
            parts.append("following prompt to be improved")
            parts.append(self.prompt)
            if self.story:
                elements_parts = []
                backgrounds = self.story.backgrounds.all()
                if backgrounds.exists():
                    elements_parts.append("Existing Locations (Backgrounds):")
                    for b in backgrounds:
                        elements_parts.append(f"- Name: {b.name}\n  Prompt: {b.prompt}")
                characters = self.story.characters.all()
                if characters.exists():
                    elements_parts.append("Existing Characters (Actors - Cast):")
                    for c in characters:
                        elements_parts.append(f"- Name: {c.name}\n  Prompt: {c.prompt}")
                props = self.story.props.all()
                if props.exists():
                    elements_parts.append("Existing Props:")
                    for p in props:
                        elements_parts.append(f"- Name: {p.name}\n  Prompt: {p.prompt}")
                if elements_parts:
                    parts.append("### STORY CONTEXT ###\nReuse these existing entities if they appear:\n" + "\n".join(elements_parts))
        return parts

    class Meta:
        ordering = ['order']




class StoryGroup(models.Model):
    story = models.ForeignKey(Story, related_name='story_groups', on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=200)
    users = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='story_groups')
    
    def __str__(self):
        return "{}".format(self.name)


class StoryProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name='story_profile', on_delete=models.CASCADE)
    story = models.ForeignKey(Story, related_name='story_profiles', on_delete=models.SET_NULL, null=True, blank=True)
    scene = models.ForeignKey(Scene, related_name='story_profiles', on_delete=models.SET_NULL, null=True, blank=True)
    group = models.ForeignKey(StoryGroup, related_name='story_profiles', on_delete=models.SET_NULL, null=True, blank=True)
    enable_filters = models.BooleanField(default=True)

    def __str__(self):
        return "{}".format(self.user.username)

    def get_current_story(self):
        story = None
        if self.story:
            story = self.story
        if self.group and self.group.story:
            story = self.group.story
        return story

class Action(models.Model, GetContentsMixin, TaskHolder):
    name = models.CharField(max_length=200, default="Action")
    scene = models.ForeignKey(Scene, related_name='actions', on_delete=models.CASCADE)
    prompt = models.TextField(null=True, blank=True)
    order = models.PositiveIntegerField(default=0, db_index=True)
    image = FilerImageField(null=True, blank=True, on_delete=models.SET_NULL, related_name='panel')
    background = models.ForeignKey(Background, related_name='actions', on_delete=models.SET_NULL, null=True, blank=True)
    actor = models.ForeignKey(Character, related_name='actions', on_delete=models.SET_NULL, null=True, blank=True)
    props = models.ManyToManyField(Prop, related_name='actions', blank=True)
    cast = models.ManyToManyField(Character, related_name='actions_cast', blank=True)
    consistent_with = models.ForeignKey('self', related_name='consistent_actions', on_delete=models.SET_NULL, null=True, blank=True)
    prompt_refine = models.TextField(null=True, blank=True)
    image_refine = FilerImageField(null=True, blank=True, on_delete=models.SET_NULL, related_name='action_refine')
    # video
    image_first = FilerImageField(null=True, blank=True, on_delete=models.SET_NULL, related_name='actions_first')
    image_last = FilerImageField(null=True, blank=True, on_delete=models.SET_NULL, related_name='actions_last')
    video = FilerFileField(null=True, blank=True, on_delete=models.SET_NULL, related_name='actions_video')
    prompt_video = models.TextField(null=True, blank=True)

    TASK_TYPE_CHOICES = settings.TASK_TYPE_CHOICES
    action = models.SlugField(choices=settings.TASK_TYPE_CHOICES, null=True, blank=True)

    prompt_comic = models.TextField(null=True, blank=True)
    image_comic = FilerImageField(null=True, blank=True, on_delete=models.SET_NULL, related_name='actions_comic')

    audio_voice = FilerFileField(null=True, blank=True, on_delete=models.SET_NULL, related_name='actions_audio')
    prompt_voice = models.TextField(null=True, blank=True)
    text = models.TextField(null=True, blank=True)
    
    def __str__(self):
        return self.get_name()
    
    def get_name(self):
        return self.name if self.name else f"#{self.id} of{self.scene.name}"

    class Meta:
        ordering = ['-order', 'name']

    def elements(self):
        props = []
        cast_members = []
        main_actor = self.actor.name if self.actor else "None"
        background = self.background.name if self.background else "None"
        if self.props:
            props.extend([prop.name for prop in self.props.all()])
        if self.cast:
            cast_members.extend([character.name for character in self.cast.all()])
        output =  f"Main Actor: <b>{main_actor}</b><br/> Background: <b>{background}</b><br/> Props: <b>{', '.join(props)}</b><br/> Cast: <b>{', '.join(cast_members)}</b><br/>"
        return mark_safe(output)
    
    def get_thumbnail(self, preset=None):
        return Image.open(self.image.path)

    def generate_comic(self, user=None):
        image_agent = Agent.objects.filter(output_type=Agent.OUTPUT_TYPE_IMAGE).first()
        out = image_agent.generate(self, preset=self.PRESET_COMIC, user=user)
        return out
    
    def get_contents(self, generate_self=True, preset=None):
        from google.genai import types
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
            out = self.prompt_voice
            if self.text is not None:
                out = f"{out} text to speak: {self.text}"
            contents['prompt'] = out
            contents['voice'] = self.actor.voice if self.actor and self.actor.voice else self.scene.voice if self.scene and self.scene.voice else None
        else:
            # preset refine is handled in the mixin
            contents = super().get_contents(generate_self=generate_self, preset=preset)
            if preset != self.PRESET_COMIC:
                if self.consistent_with:
                    contents.extend(["Maximise consistency, preserve character features and objects to the following image", self.consistent_with.get_thumbnail()])
                if self.actor:
                    contents.extend(self.actor.get_contents(generate_self=False))
                if self.cast:
                    for character in self.cast.all():
                        contents.extend(character.get_contents(generate_self=False))
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
            out = self.prompt_comic 
            if self.text is not None:
                out = f"{out} text/content: {self.text}" 
        if preset == self.PRESET_REFINE:
            return self.prompt_refine
        if not generate_self:
            return self.name
        return self.prompt
    
    def save(self, *args, **kwargs):
        print("Saving background, checking for action task: {}".format(self.action))
        action = getattr(self, 'action', None)
        if action is not None:
            self.action = None
        super().save(*args, **kwargs)
        if action is not None: 
            Task.createTaskIfQueueEnabled(
                    subject=self,
                    task_type=action
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

class Render(models.Model, TaskHolder):
    RENDER_TYPE_FILM = 'film'
    RENDER_TYPE_GRAPHIC_NOVEL = 'graphic_novel'
    RENDER_TYPE_ANIMATIC = 'animatic'

    RENDER_TYPE_CHOICES = [
        (RENDER_TYPE_FILM, 'Film'),
        (RENDER_TYPE_GRAPHIC_NOVEL, 'Graphic Novel'),
        (RENDER_TYPE_ANIMATIC, 'Animatic'),
    ]

    name = models.CharField(max_length=200, default="")
    scene = models.ForeignKey(Scene, related_name='renders', on_delete=models.CASCADE)
    video = FilerFileField(null=True, blank=True, on_delete=models.SET_NULL, related_name='render_videos')
    story = models.ForeignKey(Story, related_name='renders', on_delete=models.CASCADE)
    render_type = models.CharField(
        max_length=50,
        choices=RENDER_TYPE_CHOICES,
        default=RENDER_TYPE_FILM,
        help_text="The format in which this scene will be synthesized."
    )

    def __str__(self):
        return "{}".format(self.name)

    def _create_item_from_action(self, action, order):
        """Helper to create a RenderItem based on the current render_type."""
        item = RenderItem(
            render=self,
            scene=action.scene,
            action=action,
            order=order
        )

        if self.render_type == self.RENDER_TYPE_FILM:
            item.video = action.video
        elif self.render_type == self.RENDER_TYPE_ANIMATIC:
            item.image = action.image
            item.audio = action.audio_voice
        elif self.render_type == self.RENDER_TYPE_GRAPHIC_NOVEL:
            # Fallback to standard image if comic version isn't generated yet
            item.image = action.image_comic or action.image

        item.save()
        return item

    def refresh_render(self):
        """
        Clears existing RenderItems and recreates them. 
        Iterates through the Story's scenes if available, otherwise just the specific Scene.
        """
        self.render_items.all().delete()

        actions = []
        if self.story:
            for scene in self.story.scenes.all().order_by('order'):
                actions.extend(list(scene.actions.all().order_by('order')))
        elif self.scene:
            actions = list(self.scene.actions.all().order_by('order'))

        for i, action in enumerate(actions):
            self._create_item_from_action(action, order=i)

    class Meta:
        verbose_name = 'Render Composition'
        verbose_name_plural = 'Render Compositions'

    @classmethod
    def get_from_scene(cls, scene):
        return cls.objects.get_or_create(scene=scene, story=scene.story, defaults={'name': f"Render for {scene.name}"})[0]
        
class RenderItem(models.Model, TaskHolder):
    DEFAULT_IMAGE_DURATION = 8
    image = FilerImageField(null=True, blank=True, on_delete=models.SET_NULL, related_name='video_item')
    video = FilerFileField(null=True, blank=True, on_delete=models.SET_NULL, related_name='video_item_video')
    audio = FilerFileField(null=True, blank=True, on_delete=models.SET_NULL, related_name='video_item_audio')
    order = models.PositiveIntegerField(default=0, db_index=True)
    config = models.JSONField(null=True, blank=True)
    render = models.ForeignKey("scene.Render", related_name='render_items',null=True, blank=True, on_delete=models.CASCADE)
    scene = models.ForeignKey("scene.Scene", related_name='render_items', null=True, blank=True, on_delete=models.SET_NULL)
    action = models.ForeignKey("scene.Action", related_name='render_items', null=True, blank=True, on_delete=models.SET_NULL)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Item {self.order} for {self.render.name if self.render else 'Unassigned'}"
    
    class Meta:
        ordering = ['order']
        verbose_name = 'Render Item'
        verbose_name_plural = 'Render Items'

    @property
    def duration(self):
        out = self.DEFAULT_IMAGE_DURATION
        if self.config and 'duration' in self.config: 
            out = self.config['duration']
        return out

class ContactRequest(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.email})"