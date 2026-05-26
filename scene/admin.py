
from django.contrib import admin
from httpcore import request
from unfold.admin import ModelAdmin
from django.urls import path

from django.conf import settings
from task.models import Task
from unfold.admin import StackedInline
from .models import Character, Scene, Action, Background, StoryGroup, Style, Prop, ComicAction, RenderItem, VideoAction, Render, Story, StoryProfile, VoiceAction, Author, Nudge, ContactRequest
from .admin_utils import AjaxTaskModelAdmin
from django.utils.html import format_html
from .sections import AuthorSection, SceneSection
from .mixins import ACTION_FIELDSETS, ELEMENT_FIELDSETS, ImgShowMixin, SceneFilterMixin, StaffReadOnlyMixin, StoryFilterMixin, ViewYourOwnMixin, PromptPreviewMixin
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


@admin.action(description="Add to comic video")
def comic_to_video(modeladmin, request, queryset):
    for obj in queryset:
        render = Render.get_from_scene(obj.scene)
        RenderItem.objects.create(
            image= obj.image_comic if obj.image_comic else obj.image,
            render=render,
            order=obj.order,
        )

@admin.action(description="Add to scene video")
def video_to_scene_video(modeladmin, request, queryset):
    for obj in queryset:
        render = Render.get_from_scene(obj.scene)
        RenderItem.objects.create(
            video= obj.video,
            render=render,
            order=obj.order,
        )


@admin.action(description="Clone selected actions")
def clone(modeladmin, request, queryset):
    for obj in queryset:
        props = None
        cast = None
        many_to_many_count = 0
        if hasattr(obj, 'props'):
            props = obj.props.all()
        if hasattr(obj, 'cast'):
            cast = obj.cast.all()
        obj.pk = None
        if hasattr(obj, 'name'):
            obj.name = f"{obj.name} (Clone)"
        if hasattr(obj, 'order'):
            obj.order = obj.order + 1
        obj.save()
        if props is not None:
            obj.props.set(props)
            many_to_many_count  += obj.props.count() 
        if cast is not None:
            obj.cast.set(cast)
            many_to_many_count  += obj.cast.count()

    modeladmin.message_user(request, "Selected actions have been cloned.")

@admin.action(description="Generate image")
def default_generate_image(modeladmin, request, queryset):
    for obj in queryset:
        if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_IMAGE, owner=request.user) is None:
            obj.generate_image(user=request.user)
        modeladmin.message_user(request, "Image generated for item ID {}.".format(obj.id))

@admin.action(description="Refine image")
def default_refine_image(modeladmin, request, queryset):
    for obj in queryset:
        if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_REFINE_IMAGE, owner=request.user) is None:
            obj.refine_image(user=request.user) 
        modeladmin.message_user(request, "Image generated for item ID {}.".format(obj.id))

@admin.action(description="Refined as image")
def accept_refined_image(modeladmin, request, queryset):
    for obj in queryset:
        obj.image=obj.image_refine
        obj.save()
        modeladmin.message_user(request, "image accepted for item ID {}.".format(obj.id))

@admin.action(description="Refined as first frame")
def accept_refined_first(modeladmin, request, queryset):
    for obj in queryset:
        obj.image_first=obj.image_refine
        obj.save()
        modeladmin.message_user(request, "image accepted for item ID {}.".format(obj.id))

@admin.action(description="Refined as last frame")
def accept_refined_last(modeladmin, request, queryset):
    for obj in queryset:
        obj.image_last=obj.image_refine
        obj.save()
        modeladmin.message_user(request, "image accepted for item ID {}.".format(obj.id))

@admin.action(description="Video from image" )
def generate_video(modeladmin, request, queryset):
    for obj in queryset:
        if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_VIDEO, owner=request.user) is None:
            obj.generate_video(obj.PRESET_VIDEO, user=request.user)
        modeladmin.message_user(request, "video generated for item ID {}.".format(obj.id))

@admin.action(description="Comic from image" )
def generate_comic(modeladmin, request, queryset):
    for obj in queryset:
        if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_COMIC, owner=request.user) is None:
            obj.generate_comic(user=request.user)
        modeladmin.message_user(request, "comic generated for item ID {}.".format(obj.id))

@admin.action(description="Video from first to last")
def generate_video_first_last(modeladmin, request, queryset):
    for obj in queryset:
        if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_VIDEO_FIRST_LAST, owner=request.user) is None:
            obj.generate_video(obj.PRESET_VIDEO_FIRST_LAST, user=request.user)
        modeladmin.message_user(request, "video generated for item ID {}.".format(obj.id))

@admin.action(description="Generate Voice")
def generate_voice(modeladmin, request, queryset):
    for obj in queryset:
        if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_VOICE, owner=request.user) is None:
            obj.generate_voice(obj.PRESET_VOICE, user=request.user)
        modeladmin.message_user(request, "voice generated for item ID {}.".format(obj.id))

@admin.action(description="Generate Missing Elements Images")
def generate_scene_elements(modeladmin, request, queryset):
    for obj in queryset:
        if Task.createTaskIfQueueEnabled(obj, settings.TASK_TYPE_GENERATE_SCENE_ELEMENTS, owner=request.user) is None:
            # Manual trigger if queue is bypassed
            pass
        modeladmin.message_user(request, "Generation task for elements started for scene: {}.".format(obj.name))

@admin.action(description="Generate All Actions Images")
def generate_scene_actions(modeladmin, request, queryset):
    for obj in queryset:
        if Task.createTaskIfQueueEnabled(obj, settings.TASK_TYPE_GENERATE_SCENE_ACTIONS, owner=request.user) is None:
            # Manual trigger if queue is bypassed
            pass
        modeladmin.message_user(request, "Generation task for actions started for scene: {}.".format(obj.name))


@admin.action(description="Add me as author")
def add_me_as_author(modeladmin, request, queryset):
    for obj in queryset:
        if obj.add_author(request.user):
            self.message_user(request, f"You have been added as an author to story {obj.name}")



class AuthorInline(StackedInline):
    model = Author 
    show_count = True  # This will run `count()`
    collapsible = True
    autocomplete_fields = ['user']

@admin.register(Story)
class StoryAdmin(ModelAdmin):
    inlines = [AuthorInline]
    autocomplete_fields = ['group']
    search_fields = ['name']
    list_sections = [
        SceneSection,
        AuthorSection,
    ]
    list_display = ['__str__', 'scene_links']
    actions = [clone, add_me_as_author]
    
    def scene_links(self, obj):
        return format_html("<a href='/admin/scene/Scene/?story__id__exact={0}'>Edit ({1})</a>", obj.id, obj.scenes.count())
    scene_links.short_description = "Scenes"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change and request.user.is_authenticated:
            if obj.add_author(request.user):
                self.message_user(request, f"You have been added as an author to story {obj.name}")

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
    
@admin.register(Style)
class StyleAdmin(ModelAdmin):
    list_display = ('id','name', 'prompt')
    list_editable = ('name', 'prompt')
    list_display_links = ('id',)
    actions = [clone]
    search_fields = ['name']

@admin.register(Character)
class CharacterAdmin(PromptPreviewMixin, StoryFilterMixin, AjaxTaskModelAdmin, ImgShowMixin):
    list_display = ('name', 'pic', 'prompt', 'prompt_refine', 'last_tasks')
    list_editable = ('prompt', 'prompt_refine')
    list_display_links = ('name',)
    autocomplete_fields = ['story']
    actions = [clone, default_generate_image, default_refine_image]
    search_fields = ['name']
    fieldsets = ELEMENT_FIELDSETS
    list_sections = [PromptPreviewSection]

@admin.register(Background)
class BackgroundAdmin(StoryFilterMixin, AjaxTaskModelAdmin, ImgShowMixin):
    list_display = ('name', 'pic', 'prompt', 'prompt_refine', 'last_tasks')
    list_editable = ('prompt','prompt_refine')
    list_display_links = ('name',)
    autocomplete_fields = ['story']
    actions = [clone, default_generate_image, default_refine_image]
    search_fields = ['name']
    fieldsets = ELEMENT_FIELDSETS


@admin.register(Prop)
class PropAdmin(StoryFilterMixin, AjaxTaskModelAdmin, ImgShowMixin):
    search_fields = ['name']
    list_display = ('name', 'pic', 'prompt','prompt_refine', 'last_tasks')
    list_display_links = ('name',)
    list_editable = ('prompt','prompt_refine')
    autocomplete_fields = ['story']
    actions = [clone, default_generate_image, default_refine_image]
    search_fields = ['name']
    fieldsets = ELEMENT_FIELDSETS

@admin.register(Scene)
class SceneAdmin(StoryFilterMixin, ModelAdmin, ImgShowMixin):
    search_fields = ['name']
    list_display = ['name',  'prompt', 'prompt_refine', 'story', 'author', 'last_tasks']
    list_editable = ['prompt', 'prompt_refine']
    list_display_links = ('name',)
    autocomplete_fields = ['story', 'author']
    actions = [clone, generate_scene_elements, generate_scene_actions]
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

    @admin.display(description="Prompt")
    def my_prompt(self, obj):
        return mark_safe(f"<div class='markdown'>{markdown.markdown(obj.prompt)}</div>")
    
    @admin.display(description="Story")
    def my_story(self, obj):
        return mark_safe(f"<a href='/admin/scene/story/?id__exact={obj.story.id}'>{obj.story}</a>")

    @admin.action(description="Extract Scene")
    def extract_scene(self, request, queryset):
        for obj in queryset:
            obj.generate_scene(user=request.user)
            self.message_user(request, f"Extracting scene from contribution {obj.id} in story {obj.story.id}.")

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
            agent = obj.story.get_agent()
            if Task.createTaskIfQueueEnabled(obj, settings.TASK_TYPE_GENERATE_TEXT, thr=agent, owner=request.user) is None:
                obj.generate_text(request.user, agent)
        if request.POST.get('prompt') is not None:
            obj.prompt = request.POST.get('prompt')
            obj.save()
        return JsonResponse({'status': 'success'})


@admin.register(Author)
class AuthorAdmin(ModelAdmin):
    list_display = ['user', 'email']
    search_fields = ['user__username', 'email']

@admin.register(Nudge)
class NudgeAdmin(ModelAdmin):
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
class ActionAdmin(SceneFilterMixin, AjaxTaskModelAdmin, ImgShowMixin):
    list_display = ('get_name', 'pic', 'prompt','prompt_refine', 'last_tasks')
    list_editable = ( 'prompt', 'prompt_refine')
    list_filter = ["scene", "order"]
    ordering_field = "order"
    hide_ordering_field = True
    list_display_links = ('get_name',)
    autocomplete_fields = ['actor', 'props', 'cast', 'background', 'consistent_with', 'scene']
    search_fields = ['get_name']
    actions = [clone, default_generate_image, default_refine_image]
    fieldsets = ACTION_FIELDSETS

@admin.register(VideoAction)
class VideoActionAdmin(SceneFilterMixin, AjaxTaskModelAdmin, ImgShowMixin):
    list_display = ('name', 'pic', 'prompt_video', 'video_player','last_tasks')
    list_editable = ['prompt_video']
    list_filter = ["scene"]
    list_display_links = ('name',)
    search_fields = ['name']
    actions = [generate_video, generate_video_first_last]
    fieldsets = ACTION_FIELDSETS


@admin.register(ComicAction)
class ComicActionAdmin(SceneFilterMixin, AjaxTaskModelAdmin, ImgShowMixin):
    list_display = ('name', 'pic', 'pic_comic', 'prompt_comic', 'last_tasks')
    list_editable = ['prompt_comic']
    list_filter = ["scene"]
    list_filter = (
        'scene',
    )
    list_display_links = ('name',)
    search_fields = ['name']
    actions = [generate_comic, comic_to_video]
    fieldsets = ACTION_FIELDSETS


@admin.register(VoiceAction)
class VoiceActionAdmin(SceneFilterMixin, AjaxTaskModelAdmin, ImgShowMixin):
    list_display = ('name', 'pic', 'prompt_voice','prompt_comic',  'voice_player', 'last_tasks')
    list_editable = ['prompt_voice', 'prompt_comic']
    list_filter = ["scene"]
    list_filter = (
        'scene',
    )
    list_display_links = ('name',)
    search_fields = ['name']
    actions = [generate_voice]
    fieldsets = ACTION_FIELDSETS

@admin.register(RenderItem)
class RenderItemAdmin(ModelAdmin, ImgShowMixin):
    list_display = ('id', 'video_player', 'pic', 'config', 'order', 'render')
    list_editable = ('order', 'config')

@admin.register(Render)
class RenderAdmin(ModelAdmin, ImgShowMixin):
    @admin.action(description="Refresh Scene Video" )
    def generate_video(modeladmin, request, queryset):
        for obj in queryset:
            if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_SCENE_VIDEO) is None:
                obj.generate_video(obj.PRESET_VIDEO, user=request.user)
            modeladmin.message_user(request, "video generated for item ID {}.".format(obj.id))

    list_display = ('name', 'scene', 'render_type', 'video_player', 'video_download', 'last_tasks')
    list_display_links = ('name',)
    actions = [generate_video]
