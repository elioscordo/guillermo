
from django.contrib import admin
from httpcore import request
from unfold.admin import ModelAdmin
from django.urls import path
from django.urls import path, reverse

from django.conf import settings
from task.models import Task
from unfold.admin import StackedInline
from .models import ActionOrganizer, Character, Scene, Action, Background, SceneOrganizer, StoryGroup, Style, Prop, ComicAction, RenderItem, VideoAction, Render, Story, StoryProfile, Voice, VoiceAction, Author, Nudge, ContactRequest, WorkShop
from .admin_utils import AjaxTaskModelAdmin, AdminLinker
from django.utils.html import format_html
from .sections import AuthorSection, SceneSection, SceneElementsSection
from .mixins import ACTION_FIELDSETS, ELEMENT_FIELDSETS, SceneFilterMixin, StaffReadOnlyMixin, StoryFilterMixin, ViewYourOwnMixin, PromptPreviewMixin, AdminActionsMixin
from unfold.sections import TableSection, TemplateSection, render_to_string
from rangefilter.filters import NumericRangeFilter
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
DEFAULT_IMAGE_AGENT_NAME = "DIGA"
from django.apps import apps
from .serializers import get_generic_serializer
from django.utils.safestring import mark_safe
import markdown
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

class AjaxSectionAdminMixin:
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'ajax-section-update/',
                self.admin_site.admin_view(self.ajax_section_update_view),
                name='ajax_section_update',
            ),
        ]
        return custom_urls + urls

    def ajax_section_update_view(self, request):
        if request.method != "POST":
            return JsonResponse({"error": "Method not allowed"}, status=405)
        
        model_label = request.POST.get("_model_label")
        object_id = request.POST.get("_id")
        field_name = request.POST.get("_field")
        value = request.POST.get("_value")

        try:
            model = apps.get_model(model_label)
            obj = get_object_or_404(model, pk=object_id)
            
            # Basic validation: ensure the field exists
            if not hasattr(obj, field_name):
                return JsonResponse({"error": f"Invalid field: {field_name}"}, status=400)

            # Handle boolean conversion for checkboxes/switches if needed
            if value.lower() in ['true', 'on']: value = True
            elif value.lower() in ['false', 'off']: value = False

            setattr(obj, field_name, value)
            obj.save()
            return JsonResponse({"status": "success"})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)


class PromptPreviewSection(TemplateSection):
    """Section that renders a dropdown to preview model prompts."""
    template_name = "sections/prompt_preview.html"

    def get_context_data(self, request, instance):
        presets = []
        # Automatically discover constants starting with PRESET_ on the model
        for attr in dir(instance):
            if attr.startswith("PRESET_"):
                val = getattr(instance, attr)
                # Don't add if it's a method/callable
                if not callable(val):
                    label = attr.replace("PRESET_", "").replace("_", " ").title()
                    presets.append({"value": val, "label": label})
        
        return {
            "presets": sorted(presets, key=lambda x: x['label']),
            "instance": instance,
            "request": request,
        }
@admin.register(Style)
class StyleAdmin(AdminActionsMixin, ModelAdmin):
    list_display = ('id','name', 'prompt')
    list_editable = ('name', 'prompt')
    list_display_links = ('id',)
    actions = ['clone']
    search_fields = ['name']


class AuthorInline(StackedInline):
    model = Author 
    show_count = True  # This will run `count()`
    collapsible = True
    autocomplete_fields = ['user']

@admin.register(Story)
class StoryAdmin(AdminActionsMixin, AdminLinker, ModelAdmin):
    inlines = [AuthorInline]
    autocomplete_fields = ['group']
    search_fields = ['name']
    list_sections = [
        SceneSection,
        AuthorSection,
    ]
    list_display = ['__str__', 'image_intro','link_scenes', 'link_characters', 'link_backgrounds', 'link_props']
    actions = ['clone', 'add_me_as_author']
    fieldsets = (
        ("Write",{
            "classes": ["tab"],
            "fields": ["name", "prompt"],
        }),
        ("Refine",{
            "classes": ["tab"],
            "fields": ["prompt_refine", 'action'],
        }),
        ("Settings", {
            "classes": ["tab"],
            "fields": [ "style", "theme", "group", "render_type"],
        })
    )

    def scene_links(self, obj):
        return format_html("<a href='/admin/scene/Scene/?story__id__exact={0}'>Edit ({1})</a>", obj.id, obj.scenes.count())
    scene_links.short_description = "Scenes"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change and request.user.is_authenticated:
            if obj.add_author(request.user):
                self.message_user(request, f"You have been added as an author to story {obj.name}")


@admin.register(Scene)
class SceneAdmin(AdminActionsMixin, AdminLinker, StoryFilterMixin, AjaxTaskModelAdmin):
    search_fields = ['name']
    list_refresh = ['items']
    list_display = ['name', 'prompt', 'prompt_refine', 'last_tasks', 'items', 'link_story']
    list_editable = ['prompt', 'prompt_refine']
    list_display_links = ('name',)
    autocomplete_fields = ['story', 'author']
    actions = ['clone', 'generate_scene_elements', 'generate_scene_actions', 'extract_scene']
    list_filter = ['story',]
    fieldsets = (
        ("Write",{
            "classes": ["tab"],
            "fields": [ "prompt"],
        }),
        ("Refine",{
            "classes": ["tab"],
            "fields": ["prompt_refine", 'action'],
        }),
        ("Settings", {
            "classes": ["tab"],
            "fields": ["name", "author", "story"],
        })
    )

    def save_model(self, request, obj, form, change):
        if not obj.author and obj.story:
            author = Author.objects.filter(user=request.user, story=obj.story).first()
            if author:
                obj.author = author
        super().save_model(request, obj, form, change)

    def ajax_update_view(self, request, object_id):
        obj = get_object_or_404(self.model, pk=object_id)
        if request.POST.get('prompt_refine') is not None:
            obj.prompt_refine = request.POST.get('prompt_refine')
            obj.save()
            agent = obj.story.get_mentor()
            if Task.createTaskIfQueueEnabled(obj, settings.TASK_TYPE_GENERATE_TEXT, thr=agent, owner=request.user) is None:
                obj.generate_text(request.user, agent)
        if request.POST.get('prompt') is not None:
            obj.prompt = request.POST.get('prompt')
            obj.save()
        return JsonResponse({'status': 'success'})


@admin.register(StoryGroup)
class StoryGroupAdmin(ModelAdmin):
    list_display = ('id', 'name', 'story')
    list_editable = ('name', 'story')
    list_display_links = ('id',)
    autocomplete_fields = ['story', 'users']
    search_fields = ['name']

@admin.register(StoryProfile)
class StoryProfileAdmin(ViewYourOwnMixin, StaffReadOnlyMixin, ModelAdmin):
    list_display = ('id', 'user','group', 'story', 'scene' )
    list_display_links = ('id',)
    autocomplete_fields = ['story', 'group', 'user', 'scene']
    staff_readonly_fields = ['user']
    

@admin.register(Character)
class CharacterAdmin(AdminActionsMixin, PromptPreviewMixin, StoryFilterMixin, AjaxTaskModelAdmin):
    list_display = ('name', 'pic', 'prompt', 'prompt_refine', 'last_tasks')
    list_refresh = ['pic']
    list_editable = ('prompt', 'prompt_refine')
    list_display_links = ('name',)
    autocomplete_fields = ['story']
    list_filter = ['story', 'id']
    actions = ['clone', 'default_generate_image', 'default_refine_image']
    search_fields = ['name']
    fieldsets = ELEMENT_FIELDSETS
    list_sections = [PromptPreviewSection]

@admin.register(Background)
class BackgroundAdmin(AdminActionsMixin, StoryFilterMixin, AjaxTaskModelAdmin):
    list_display = ('name', 'pic', 'prompt', 'prompt_refine', 'last_tasks')
    list_refresh = ['pic']
    list_editable = ('prompt','prompt_refine')
    list_display_links = ('name',)
    autocomplete_fields = ['story']
    list_filter = ['story', 'id']
    actions = ['clone', 'default_generate_image', 'default_refine_image']
    search_fields = ['name']
    fieldsets = ELEMENT_FIELDSETS


@admin.register(Prop)
class PropAdmin(AdminActionsMixin, StoryFilterMixin, AjaxTaskModelAdmin):
    search_fields = ['name']
    list_refresh = ['pic']
    list_display = ('name', 'pic', 'prompt','prompt_refine', 'last_tasks')
    list_display_links = ('name',)
    list_editable = ('prompt','prompt_refine')
    autocomplete_fields = ['story']
    list_filter = ['story', 'id']
    actions = ['clone', 'default_generate_image', 'default_refine_image']
    search_fields = ['name']
    fieldsets = ELEMENT_FIELDSETS


@admin.register(Author)
class AuthorAdmin(AdminActionsMixin, ModelAdmin):
    list_display = ['user', 'email', 'story', 'scene_count']
    list_editable = ['story']
    list_display_links = ('user',)
    autocomplete_fields = ['user', 'story']
    search_fields = ['user__username', 'email']

@admin.register(Nudge)
class NudgeAdmin(AdminActionsMixin, ModelAdmin):
    list_display = ["id", 'sender', 'receiver', 'story', 'message']
    fieldsets = (
        ("Write",{
            "classes": ["tab"],
            "fields": ["message", ],
        }),
        ("Settings", {
            "classes": ["tab"],
            "fields": ["receiver", "sender", "story"],
        })
    )

@admin.register(Action)
class ActionAdmin(AdminActionsMixin, SceneFilterMixin, AjaxTaskModelAdmin):
    list_display = ('get_name', 'pic', 'prompt','prompt_refine', 'last_tasks')
    list_refresh = ['pic']
    list_editable = ( 'prompt', 'prompt_refine')
    list_filter = ["scene", "order", "id"]
    ordering_field = "order"
    hide_ordering_field = True
    list_display_links = ('get_name',)
    autocomplete_fields = ['actor', 'props', 'cast', 'background', 'consistent_with', 'scene']
    search_fields = ['get_name']
    actions = ['clone', 'default_generate_image', 'default_refine_image']
    fieldsets = ACTION_FIELDSETS

@admin.register(VideoAction)
class VideoActionAdmin(AdminActionsMixin, SceneFilterMixin, AjaxTaskModelAdmin):
    list_display = ('name', 'pic', 'prompt_video', 'video_player','last_tasks')
    list_editable = ['prompt_video']
    list_filter = ["scene"]
    list_display_links = ('name',)
    search_fields = ['name']
    actions = ['generate_video', 'generate_video_first_last']
    fieldsets = ACTION_FIELDSETS

@admin.register(ActionOrganizer)
class ActionOrganizerAdmin(AdminActionsMixin, SceneFilterMixin, ModelAdmin):
    list_display = ('id', 'name', 'pic', 'scene', 'is_intro')
    list_editable = ['name',  'scene','is_intro']
    list_filter = ["scene"]
    search_fields = ['name']

@admin.register(SceneOrganizer)
class SceneOrganizerAdmin(AdminActionsMixin, AdminLinker, SceneFilterMixin, ModelAdmin):
    list_display = ('id', 'name', 'image_intro', 'link_actions', 'story')
    list_editable = ['name',  'story']
    list_filter = ["story"]
    search_fields = ['name']

@admin.register(ComicAction)
class ComicActionAdmin(AdminActionsMixin, SceneFilterMixin, AjaxTaskModelAdmin):
    list_display = ('name', 'pic', 'pic_comic', 'prompt_comic', 'last_tasks')
    list_editable = ['prompt_comic']
    list_filter = ["scene"]
    list_filter = (
        'scene',
    )
    list_display_links = ('name',)
    search_fields = ['name']
    actions = ['generate_comic', 'comic_to_video']
    fieldsets = ACTION_FIELDSETS


@admin.register(Voice)
class VoiceAdmin(AdminActionsMixin, ModelAdmin):
    list_display = ('name','prompt', 'code', 'sample_text', 'voice_player', 'last_tasks')
    list_display_links = ('name',)
    actions = ['generate_voice']

@admin.register(VoiceAction)
class VoiceActionAdmin(AdminActionsMixin, SceneFilterMixin, AjaxTaskModelAdmin):
    list_display = ('name', 'pic', 'prompt_voice','prompt_comic',  'voice_player', 'last_tasks')
    list_editable = ['prompt_voice', 'prompt_comic']
    list_filter = ["scene"]
    list_filter = (
        'scene',
    )
    list_display_links = ('name',)
    search_fields = ['name']
    actions = ['generate_voice']
    fieldsets = ACTION_FIELDSETS

@admin.register(RenderItem)
class RenderItemAdmin(ModelAdmin):
    list_display = ('id', 'video_player', 'pic', 'config', 'order', 'render')
    list_editable = ('order', 'config')

@admin.register(Render)
class RenderAdmin(AdminActionsMixin, ModelAdmin):
    list_display = ('name', 'scene', 'render_type', 'video_player', 'video_download', 'last_tasks')
    list_display_links = ('name',)
    actions = ['refresh_scene_video']


@admin.register(ContactRequest)
class ContactRequestAdmin(ModelAdmin):
    pass

@admin.register(WorkShop)
class WorkShopAdmin(ModelAdmin):
    pass