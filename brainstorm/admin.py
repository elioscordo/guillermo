from django.contrib import admin
from django.conf import settings
from django.http import JsonResponse
from django.utils.html import format_html, strip_tags
from django.views.decorators.cache import never_cache
from task.models import Task
from .models import Script, Nudge, Theme, Contribution, Author
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


class AuthorInline(StackedInline):
    model = Author 
    show_count = True  # This will run `count()`
    collapsible = True
    autocomplete_fields = ['user']

class AuthorTableSection(TableSection):
    model = Author
    NO_USER_LABEL = "Use Create User Action"
    verbose_name = "Authors"
    
    def name(self, obj):
        return f"{obj.user.username if obj.user else obj.email}"
    
    def scenes(self, obj):
        turn_type = Script.STATE_SCENE
        turn_link = self.NO_USER_LABEL
        if obj.user:
            turn_link = format_html("<a href='/admin/brainstorm/contribution/?script__id__exact={0}&author__id__exact={1}&type__exact=scene'>{2}</a>", obj.script.id, obj.id, obj.contributions.filter(type=turn_type).count())
            if (obj.user == self.request.user):
                add_link = format_html("<a href='/admin/brainstorm/contribution/add/?script={0}&author={1}&type={2}'>[+]</a>", obj.script.id, obj.id, turn_type)
                turn_link = format_html("{} {}", turn_link, add_link)
        return mark_safe(turn_link)
    
    def plots(self, obj):
        turn_type = Script.STATE_PLOT
        turn_link = self.NO_USER_LABEL
        if obj.user:
            turn_link = format_html("<a href='/admin/brainstorm/contribution/?script__id__exact={0}&author__id__exact={1}&type__exact=plot'>{2}</a>", obj.script.id, obj.id, obj.contributions.filter(type=turn_type).count())
            if (obj.user == self.request.user):
                add_link = format_html("<a href='/admin/brainstorm/contribution/add/?script={0}&author={1}&type={2}'>[+]</a>", obj.script.id, obj.id, turn_type)
                turn_link = format_html("{} {}", turn_link, add_link)
        return mark_safe(turn_link)
    
    def nudges(self, obj):
        nudge_link = self.NO_USER_LABEL
        if obj.user:
            nudge_count = obj.user.received_nudges.count()
            nudge_link = format_html("<a href='/admin/brainstorm/nudge/?receiver__id__exact={0}'>{1}</a>", obj.user.id, nudge_count) 
            if (obj.user != self.request.user):
                add_link = format_html("<a href='/admin/brainstorm/nudge/add/?receiver={0}&script={1}&sender={2}'>-></a>", obj.user.id, obj.script.id, self.request.user.id)
                nudge_link = format_html("{} {}", nudge_link, add_link)
        return mark_safe(nudge_link)
    
    fields = ['name', 'scenes', 'plots', 'nudges']
    extra = 0
    show_count = True  # This will run `count()`
    collapsible = True
    related_name = 'authors'

class ThemeSection(TemplateSection):
    template_name ="sections/prompt.html"
    
    def get_context_data(self, request, instance) -> dict[str, Any]:
        return {
            "item" : instance.theme,
            "request": request,
        }


class ContributionTableSection(TableSection):
    template_name ="sections/contribution.html"

    def context_data(self) -> dict:
        return {
            "script": self.instance,
            "author": self.request.user.authors.filter(script=self.instance).first()
        }
    def name(self, obj):
        return f"{obj.user.username if obj.user else obj.email}"
    
    def height(self, obj):
        return "230px"

    def prompt(self, obj):
        return mark_safe(f"<div class='markdown'>{markdown.markdown(obj.prompt)}</div>")
    
    fields = ['prompt', 'author', 'type']
    extra = 0
    show_count = True  # This will run `count()`
    collapsible = False
    related_name = 'contributions'

@admin.register(Theme)
class ThemeAdmin(ModelAdmin):
    search_fields = ['name']
    
    def action_scripts(self, obj):
        return format_html("<a href='/admin/brainstorm/script/?theme__id__exact={0}'>{1} scripts</a>", obj.id, obj.script_set.count())

@admin.register(Script)
class ScriptAdmin(ModelAdmin):
    exclude = ('state',)
    inlines = [AuthorInline]
    autocomplete_fields = ['group']
    list_sections = [
        ContributionTableSection,
        AuthorTableSection,
        ThemeSection
    ]
    list_display = ['__str__', 'turns_links']

    def turns_links(self, obj):
        return format_html("<a href='/admin/brainstorm/contribution/?script__id__exact={0}'>Edit ({1})</a>", obj.id, obj.contributions.count())
    turns_links.short_description = "Contributions"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change and request.user.is_authenticated:
            if not obj.authors.filter(user=request.user).exists():
                Author.objects.create(script=obj, user=request.user)


@admin.register(Contribution)
class ContributionAdmin(AjaxTaskModelAdmin):
    
    fieldsets = (
        ("Write",{
            "classes": ["tab"],
            "fields": ["prompt", ],
        }),
        ("Settings", {
            "classes": ["tab"],
            "fields": ["author", "script", "type", "prompt_refine", "agent"],
        })
    )

    @admin.display(description="Prompt")
    def my_prompt(self, obj):
        return mark_safe(f"<div class='markdown'>{markdown.markdown(obj.prompt)}</div>")

    @admin.display(description="Script")
    def my_script(self, obj):
        return mark_safe(f"<a href='/admin/brainstorm/script/?id__exact={obj.script.id}'>{obj.script}</a>")

    list_display = ['id', 'prompt', 'prompt_refine', 'last_tasks', 'my_script', 'author']
    list_editable = ['prompt', 'prompt_refine']
    
    list_filter = ['script',]
    actions = ['extract_scene']

    @admin.action(description="Extract Scene")
    def extract_scene(self, request, queryset):
        for obj in queryset:
            obj.generate_scene(user=request.user)
            self.message_user(request, f"Extracting scene from contribution {obj.id} in script {obj.script.id}.")

    def save_model(self, request, obj, form, change):
        if not obj.author and obj.script:
            author = Author.objects.filter(user=request.user, script=obj.script).first()
            if author:
                obj.author = author
        super().save_model(request, obj, form, change)

    def ajax_update_view(self, request, object_id):
        # Implementation of the view logic from step 1
        # Use 'self' instead of passing model_admin
        obj = get_object_or_404(self.model, pk=object_id)
        if request.POST.get('prompt_refine') is not None:
            obj.prompt_refine = request.POST.get('prompt_refine')
            obj.save()
            agent = obj.script.get_agent()
            if Task.createTaskIfQueueEnabled(obj, settings.TASK_TYPE_GENERATE_TEXT, thr=agent, owner=request.user) is None:
                obj.generate_text(request.user, agent)
        if request.POST.get('prompt') is not None:
            obj.prompt = request.POST.get('prompt')
            obj.save()
        return JsonResponse({'status': 'success'})


@admin.register(Author)
class AuthorAdmin(ModelAdmin):
    list_display = ['user', 'email']

@admin.register(Nudge)
class NudgeAdmin(ModelAdmin):
    list_display = ["id", 'sender', 'receiver', 'script', 'message']
    fieldsets = (
        ("Write",{
            "classes": ["tab"],
            "fields": ["message", ],
        }),
        ("Settings", {
            "classes": ["tab"],
            "fields": ["receiver", "sender", "script"],
        })
    )