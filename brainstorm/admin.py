from django.contrib import admin
from django.conf import settings
from django.utils.html import format_html, strip_tags
from django.views.decorators.cache import never_cache
from task.models import Task
from .models import Session, Nudge, Theme, Turn, Participant
from .mixins import UserCreatorMixin
from unfold.admin import Any, HttpRequest, ModelAdmin
from scene.admin import AjaxSectionAdminMixin, AjaxTableSection
from unfold.admin import StackedInline
from unfold.sections import TemplateSection, render_to_string
from django.utils.safestring import mark_safe
from .sections import TableSection
from scene.admin import AjaxTaskModelAdmin

from django.shortcuts import get_object_or_404
import markdown


class ParticipantInline(StackedInline):
    model = Participant 
    show_count = True  # This will run `count()`
    collapsible = True
    autocomplete_fields = ['user']

class ParticipantTableSection(TableSection):
    model = Participant
    NO_USER_LABEL = "Use Create User Action"
    verbose_name = "Participants"
    
    def name(self, obj):
        return f"{obj.user.username if obj.user else obj.email}"
    
    def scenes(self, obj):
        turn_type = Session.STATE_SCENE
        turn_link = self.NO_USER_LABEL
        if obj.user:
            turn_link = format_html("<a href='/admin/brainstorm/turn/?session__id__exact={0}&participant__id__exact={1}&type__exact=scene'>{2}</a>", obj.session.id, obj.id, obj.turns.filter(type=turn_type).count())
            if (obj.user == self.request.user):
                add_link = format_html("<a href='/admin/brainstorm/turn/add/?session={0}&participant={1}&type={2}'>[+]</a>", obj.session.id, obj.id, turn_type)
                turn_link = format_html("{} {}", turn_link, add_link)
        return mark_safe(turn_link)
    
    def plots(self, obj):
        turn_type = Session.STATE_PLOT
        turn_link = self.NO_USER_LABEL
        if obj.user:
            turn_link = format_html("<a href='/admin/brainstorm/turn/?session__id__exact={0}&participant__id__exact={1}&type__exact=plot'>{2}</a>", obj.session.id, obj.id, obj.turns.filter(type=turn_type).count())
            if (obj.user == self.request.user):
                add_link = format_html("<a href='/admin/brainstorm/turn/add/?session={0}&participant={1}&type={2}'>[+]</a>", obj.session.id, obj.id, turn_type)
                turn_link = format_html("{} {}", turn_link, add_link)
        return mark_safe(turn_link)
    
    def nudges(self, obj):
        nudge_link = self.NO_USER_LABEL
        if obj.user:
            nudge_count = obj.user.received_nudges.count()
            nudge_link = format_html("<a href='/admin/brainstorm/nudge/?receiver__id__exact={0}'>{1}</a>", obj.user.id, nudge_count) 
            if (obj.user != self.request.user):
                add_link = format_html("<a href='/admin/brainstorm/nudge/add/?receiver={0}&session={1}&sender={2}'>-></a>", obj.user.id, obj.session.id, self.request.user.id)
                nudge_link = format_html("{} {}", nudge_link, add_link)
        return mark_safe(nudge_link)
    
    fields = ['username', 'scenes', 'plots', 'nudges']
    extra = 0
    show_count = True  # This will run `count()`
    collapsible = True
    related_name = 'participants'

class ParticipantStoryTableSection(TableSection):
    
    def name(self, obj):
        return f"{obj.user.username if obj.user else obj.email}"
    
    fields = ['name', 'prompt']
    extra = 0
    show_count = True  # This will run `count()`
    collapsible = False
    related_name = 'story'

    def height(self, obj):
        return "230px"

class ThemeSection(TemplateSection):
    template_name ="sections/prompt.html"
    
    def get_context_data(self, request, instance) -> dict[str, Any]:
        return {
            "item" : instance.theme,
            "request": request,
        }


class TurnTableSection(TableSection):
    template_name ="sections/turn.html"

    def context_data(self) -> dict:
        return {
            "session": self.instance,
            "participant": self.request.user.participants.filter(session=self.instance).first()
        }
    def name(self, obj):
        return f"{obj.user.username if obj.user else obj.email}"
    
    def height(self, obj):
        return "230px"

    def prompt(self, obj):
        return mark_safe(f"<div class='markdown'>{markdown.markdown(obj.prompt)}</div>")
    
    fields = ['prompt', 'participant', 'type']
    extra = 0
    show_count = True  # This will run `count()`
    collapsible = False
    related_name = 'turns'

@admin.register(Theme)
class ThemeAdmin(ModelAdmin):
    search_fields = ['name']
    
    def action_sessions(self, obj):
        return format_html("<a href='/admin/brainstorm/session/?theme__id__exact={0}'>{1} sessions</a>", obj.id, obj.sessions.count())

@admin.register(Session)
class SessionAdmin(ModelAdmin, ):
    exclude = ('state',)
    inlines = [ParticipantInline]
    autocomplete_fields = ['group']
    list_sections = [
        TurnTableSection,
        ParticipantTableSection,
        ThemeSection
    ]
    list_display = ['__str__', 'turns_links']

    def turns_links(self, obj):
        return format_html("<a href='/admin/brainstorm/turn/?session__id__exact={0}'>Edit Contributions ({1})</a>", obj.id, obj.turns.count())
    turns_links.short_description = "Contributions"


@admin.register(Turn)
class TurnAdmin(AjaxTaskModelAdmin):
    
    fieldsets = (
        ("Write",{
            "classes": ["tab"],
            "fields": ["prompt", ],
        }),
        ("Settings", {
            "classes": ["tab"],
            "fields": ["participant", "session", "type", "prompt_refine", "agent"],
        })
    )

    @admin.display(description="Prompt")
    def my_prompt(self, obj):
        return mark_safe(f"<div class='markdown'>{markdown.markdown(obj.prompt)}</div>")

    @admin.display(description="Session")
    def my_session(self, obj):
        return mark_safe(f"<a href='/admin/brainstorm/session/?id__exact={obj.session.id}'>{obj.session}</a>")

    list_display = ['id', 'my_session', 'participant',  'my_prompt', 'prompt_refine', 'last_tasks' ]
    list_editable = ['prompt_refine']
    
    list_filter = ['session',]

    def save_model(self, request, obj, form, change):
        if not obj.participant and obj.session:
            participant = Participant.objects.filter(user=request.user, session=obj.session).first()
            if participant:
                obj.participant = participant
        super().save_model(request, obj, form, change)

    @never_cache
    def ajax_update_view(self, request, object_id):
        # Implementation of the view logic from step 1
        # Use 'self' instead of passing model_admin
        obj = get_object_or_404(self.model, pk=object_id)
        if request.POST.get('prompt_refine') is not None:
            obj.prompt_refine = request.POST.get('prompt_refine')
            obj.save()
            if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_TEXT, thr=obj.session.get_agent(), owner=request.user) is None:
                obj.generate_text()
   

@admin.register(Participant)
class ParticipantAdmin(ModelAdmin):
    list_display = ['user', 'email']

@admin.register(Nudge)
class NudgeAdmin(ModelAdmin):
    list_display = ["id", 'sender', 'receiver', 'session', 'message']
    fieldsets = (
        ("Write",{
            "classes": ["tab"],
            "fields": ["message", ],
        }),
        ("Settings", {
            "classes": ["tab"],
            "fields": ["receiver", "sender", "session"],
        })
    )