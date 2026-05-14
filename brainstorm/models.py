import email

from django.db import models
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
from brainstorm.mixins import EmailSenderMixin, UserCreatorMixin            
from task.models import TaskHolder
from agent.models import Agent
from agent.models import GetContentsMixin

def dashboard_callback(request, context):
    session = []
    if request.user.is_authenticated:
            sessions =  Session.objects.filter(participants__user=request.user).distinct()
    context.update({'sessions':sessions})
    return context

class Theme(models.Model):
    name = models.CharField(max_length=100, default='New Game')
    prompt = models.TextField(null=True, blank=True)
    
    def __str__(self):
        return "{}".format(self.name)

class Nudge(models.Model, EmailSenderMixin):
    email_template = 'email/nudge.html'

    sender = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='sent_nudges', on_delete=models.CASCADE, null=True, blank=True)
    receiver = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='received_nudges', on_delete=models.CASCADE, null=True, blank=True)
    session = models.ForeignKey('Session', related_name='nudges', on_delete=models.CASCADE, null=True, blank=True)
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
            participant = Participant.objects.filter(session=self.session, user=self.receiver).first()
            cta_url = ""
            if participant:
                cta_url = settings.SITE_URL + f'/admin/brainstorm/turn/add?session={self.session.id}&participant={participant.id}&type={self.session.turn_type()}'
            
            self.send_email(
                subject=f"Brainstorming: {self.session.theme.name}. {self.sender.username} nudged you!",
                context={
                    'item': self,
                    'cta': cta_url
                },
                recipient_list=[self.receiver.email]
            )
        super().save(*args, **kwargs)

class Session(models.Model):
    name = models.CharField(max_length=100, null=True, blank=True,help_text="When time comes give it a name to remember it by!")
    theme = models.ForeignKey('Theme', on_delete=models.CASCADE, null=True, blank=True)
    group = models.ForeignKey('scene.StoryGroup', help_text="Auto create participants from this group, it happens only when the session is saved for the first time",  on_delete=models.CASCADE, null=True, blank=True)
    
    STATE_SCENE = 'scene'
    STATE_PLOT = 'plot'   
    STATE_FINISHED = 'finished'
    
    STATES = [
        (STATE_SCENE, 'Scene'),
        (STATE_PLOT, 'Plots'),
        (STATE_FINISHED, 'Finished')
    ]
    state = models.CharField(max_length=100, choices=STATES, default=STATE_SCENE)

    class Meta:
        verbose_name = 'Script'
        verbose_name_plural = 'Scripts'

    def __str__(self):
        return "{}".format(self.name if self.name else f"{self.id} ({self.theme.name})" if self.theme else "Script {}".format(self.id)  )
    
    def import_group_members(self):
        if self.group is not None:
            for member in self.group.users.all():
                if not Participant.objects.filter(session=self, user=member).exists():
                    Participant.objects.create(session=self, user=member)

    def save(self, *args, **kwargs):
        do_import = not self.id and self.group is not None
        super().save(*args, **kwargs)
        if do_import:
            self.import_group_members()

    def turn_type(self):
        if self.state in [self.STATE_SCENE, self.STATE_PLOT]:
            return self.state
        return self.STATE_SCENE

    def get_agent(self):
        agent = Agent.objects.filter(output_type=Agent.OUTPUT_TYPE_TEXT).first()
        return agent

class Participant(models.Model, UserCreatorMixin):
    session = models.ForeignKey('Session', related_name='participants', on_delete=models.CASCADE, null=True, blank=True)
    order = models.IntegerField(default=0)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='participants', on_delete=models.CASCADE, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.email and not self.user:
            raise ValueError("Either email or user must be provided.")
        if self.email and self.user is None:
            user = self.create_user(self.session, self.email)
            self.user = user
        super().save(*args, **kwargs)
           

    def __str__(self):
        return "{}".format(self.user.username if self.user else self.email)

    def username(self):
        return self.user.username if self.user else self.email

class Turn(models.Model, TaskHolder, GetContentsMixin):
    TYPE_HELP = 'help'
    TURN_TYPES = [
        (Session.STATE_SCENE, 'Scene'),
        (Session.STATE_PLOT, 'Plot'),
        (TYPE_HELP, 'Help')
    ]

    type = models.CharField(max_length=100, choices=TURN_TYPES, default=Session.STATE_SCENE)
    prompt = models.TextField(null=True, default="#Location\n#Characters\n#Actions\n", blank=True)
    prompt_refine = models.TextField(null=True, blank=True)
    session = models.ForeignKey('Session', related_name='turns', on_delete=models.CASCADE, null=True, blank=True)
    participant = models.ForeignKey('Participant', related_name='turns', on_delete=models.CASCADE, null=True, blank=True)
    agent = models.ForeignKey('agent.Agent', on_delete=models.CASCADE, null=True, blank=True)
    pass_turn = models.BooleanField(default=False, help_text="If true, the turn will be passed to the next player")
    
    def __str__(self):
        return "{}".format(self.participant.user.username if self.participant and self.participant.user else "Turn {}".format(self.id))

    def generate_text(self, user, agent):
        prompt = agent.generate(self, preset=self.PRESET_REFINE_PROMPT, user=user)
        self.prompt = prompt
        self.save()
        return prompt
    

    def get_contents(self, generate_self=True, preset=None):
         # remove generate self and add preset regenerate_image
        parts = [self.prompt_refine]
        parts.append("following prompt to be improved")
        parts.append(self.prompt)
        return parts
       
"""    def save(self, *args, **kwargs):
        if not self.game and self.player:
            self.game = self.player.game
        if self.session and self.session.state == Session .STATE_FINISHED:
            raise ValueError("Cannot add turns to a finished game.")
        self.session.should_play(self.player, self.type)
        super().save(*args, **kwargs)
"""


class ContactRequest(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.email})"

     