import email

from django.db import models
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
from brainstorm.mixins import EmailSenderMixin, UserCreatorMixin            
from task.models import TaskHolder
from agent.models import Agent
from agent.models import GetContentsMixin
from scene.models import Scene, Story, Style
        
def dashboard_callback(request, context):
    scripts = []
    if request.user.is_authenticated:
            scripts =  Script.objects.filter(authors__user=request.user).distinct()
    context.update({'scripts': scripts})
    return context


class Script(models.Model):
    name = models.CharField(max_length=100, null=True, blank=True,help_text="When time comes give it a name to remember it by!")
    theme = models.ForeignKey('Theme', on_delete=models.CASCADE, null=True, blank=True)
    group = models.ForeignKey('scene.StoryGroup', help_text="Auto create authors from this group, it happens only when the script is saved for the first time",  on_delete=models.CASCADE, null=True, blank=True)
    story = models.ForeignKey('scene.Story', null=True, blank=True, related_name='scripts', on_delete=models.SET_NULL)
    style = models.ForeignKey(Style, related_name='scripts', null=True, blank=True, on_delete=models.SET_NULL)
    
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
        help_text="The default render format for stories generated from this script."
    )
    
    class Meta:
        verbose_name = 'Script'
        verbose_name_plural = 'Scripts'

    def __str__(self):
        return self.get_name()
    
    def get_name(self):
        return self.name if self.name else f"{self.id} ({self.theme.name})" if self.theme else "Script {}".format(self.id)
    
    def import_group_members(self):
        if self.group is not None:
            for member in self.group.users.all():
                if not Author.objects.filter(script=self, user=member).exists():
                    Author.objects.create(script=self, user=member)

    def save(self, *args, **kwargs):
        if not self.style:
            default_style = Style.objects.filter(global_default=True).first()
            if default_style:
                self.style = default_style
                
        do_import = not self.id and self.group is not None
        super().save(*args, **kwargs)
        if do_import:
            self.import_group_members()

    def contribution_type(self):
        return 'scene'

    def get_agent(self):
        agent = Agent.objects.filter(output_type=Agent.OUTPUT_TYPE_TEXT).first()
        return agent

    def get_story(self):
        if self.story is None:
            name = self.get_name()
            self.story = Story.objects.create(
                name=name,
                render_type=self.render_type,
                style=self.style
            )
            self.save()
        return self.story

class Contribution(models.Model, TaskHolder, GetContentsMixin):
    TYPE_HELP = 'help'
    CONTRIBUTION_TYPES = [
        ('scene', 'Scene'),
        ('plot', 'Plot'),
        (TYPE_HELP, 'Help')
    ]

    type = models.CharField(max_length=100, choices=CONTRIBUTION_TYPES, default='scene')
    prompt = models.TextField(null=True, default="#Location\n#Cast\n#Props\n#Actions\n", blank=True)
    prompt_refine = models.TextField(null=True, blank=True)
    author = models.ForeignKey('Author', related_name='contributions', on_delete=models.CASCADE, null=True, blank=True)
 
    script = models.ForeignKey('Script', related_name='contributions', on_delete=models.CASCADE, null=True, blank=True)
    agent = models.ForeignKey('agent.Agent', on_delete=models.CASCADE, null=True, blank=True)
    pass_turn = models.BooleanField(default=False, help_text="If true, the turn will be passed to the next player")
    scene = models.ForeignKey('scene.Scene', null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return "{}".format(self.author.user.username if self.author and self.author.user else "Contribution {}".format(self.id))

    def generate_text(self, user, agent):
        prompt = agent.generate(self, preset=self.PRESET_REFINE_PROMPT, user=user)
        self.prompt = prompt
        self.save()
        return prompt

    def get_contents(self, generate_self=True, preset=None):
        parts = []
        if preset == self.PRESET_REFINE_PROMPT:
            parts = [self.prompt_refine]
            parts.append("following prompt to be improved")
        parts.append(self.prompt)
        story = self.get_story()
        if story:
            elements_parts = []
            backgrounds = story.backgrounds.all()
            if backgrounds.exists():
                elements_parts.append("Existing Locations (Backgrounds):")
                for b in backgrounds:
                    elements_parts.append(f"- Name: {b.name}\n  Prompt: {b.prompt}")
            
            characters = story.characters.all()
            if characters.exists():
                elements_parts.append("Existing Characters (Actors - Cast):")
                for c in characters:
                    elements_parts.append(f"- Name: {c.name}\n  Prompt: {c.prompt}")
            
            props = story.props.all()
            if props.exists():
                elements_parts.append("Existing Props:")
                for p in props:
                    elements_parts.append(f"- Name: {p.name}\n  Prompt: {p.prompt}")
            if elements_parts:
                parts.append("### STORY CONTEXT ###\nReuse these existing entities if they appear:\n" + "\n".join(elements_parts))
        return parts

    def get_story(self):
        return self.script.get_story()
    
    def get_scene(self, creation_name=None): 
        if self.scene is None:
            if creation_name is None:
                creation_name = f"Exported from {self.id}"
            self.scene = Scene.objects.create(name=creation_name, story=self.get_story())
            self.save()
        return self.scene
    


class ContactRequest(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.email})"

     