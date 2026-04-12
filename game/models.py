
from django.db import models

from agent.models import Agent

class Player(models.Model):
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE, null=True, blank=True)
    order = models.IntegerField(default=0)
    group = models.ForeignKey('PlayerGroup', on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        ordering = ['order']

class PlayerGroup(models.Model):
    name = models.CharField(max_length=100, default="")
    def __str__(self):
        return "{}".format(self.name)
    
    def context_text(self, generate_self=True, preset=None):
        if preset == self.PRESET_REFINE:
            return self.prompt_refine
        return self.prompt


class Game(models.Model):
    STATE_READY = 'ready'
    STATE_HINT = 'hint'
    STATE_PLOT = 'plot'   
    STATE_FINISHED = 'finished'
    
    name = models.CharField(max_length=100, default="")
    state = models.CharField(max_length=100, choices=[
        (STATE_READY, 'Ready'),
        (STATE_HINT, 'Hints'),
        (STATE_PLOT, 'Plots'),
        (STATE_FINISHED, 'Finished')
    ], default=STATE_READY)

    group = models.ForeignKey('PlayerGroup', on_delete=models.CASCADE, null=True, blank=True)
    turn_duration = models.DurationField(null=True, blank=True)
    start = models.DateTimeField(null=True, blank=True)
    end = models.DateTimeField(null=True, blank=True)

    joker = models.ForeignKey(Agent, on_delete=models.CASCADE, null=True, blank=True, related_name='jocker_games')
    assistant = models.ForeignKey(Agent, on_delete=models.CASCADE, null=True, blank=True, related_name='assistant_games')

    def should_play(self, player, turn_type):
        if self.state != turn_type:
            return False
        turns = self.turn_set.filter(player=player).order_by('-start')
        if turns.count() == 0:
            return True
        last_turn = turns.first()
        return last_turn.end is not None
    
    def __str__(self):
        return "{}".format(self.name)

class Turn(models.Model):
    TYPE_HINT = 'hint'
    TYPE_PLOT = 'plot'
    TYPE_HELP = 'help'
    TYPE_JOKE = 'joke'
    
    name = models.CharField(max_length=100, default="")
    type = models.CharField(max_length=100, choices=[
        (TYPE_HINT, 'Hint'),
        (TYPE_PLOT, 'Plot'),
        (TYPE_HELP, 'Help'),
        (TYPE_JOKE, 'Joke')
    ], default=TYPE_HINT)

    prompt = models.TextField(null=True, blank=True)
    game = models.ForeignKey('Game', on_delete=models.CASCADE, null=True, blank=True)
    player = models.ForeignKey('Player', on_delete=models.CASCADE, null=True, blank=True)
    finished = models.BooleanField(default=False)
    start = models.DateTimeField(null=True, blank=True)
    end = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.game and self.game.state == Game.STATE_FINISHED:
            raise ValueError("Cannot add turns to a finished game.")
        if not self.game.should_play(self.player, self.type):
            raise ValueError("It's not the player's turn or the turn type is not allowed.")
        super().save(*args, **kwargs)

    def __str__(self):
        return "{}".format(self.name)
