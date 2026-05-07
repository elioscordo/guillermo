
from django.contrib import admin
from httpcore import request
from unfold.admin import ModelAdmin
from django.conf import settings
from task.models import Task
from django.urls import path
from .models import Character, Scene, Action, Background, StoryGroup, Style, Prop, ComicAction, VideoItem, VideoAction, SceneVideo, Story, StoryProfile, VoiceAction
from django.utils.html import format_html
from .mixins import ACTION_FIELDSETS, ELEMENT_FIELDSETS, ImgShowMixin, SceneFilterMixin, StaffReadOnlyMixin, StoryFilterMixin, ViewYourOwnMixin
from unfold.sections import TableSection, render_to_string
from rangefilter.filters import NumericRangeFilter
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
DEFAULT_IMAGE_AGENT_NAME = "DIGA"
from django.apps import apps

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

class AjaxTableSection(TableSection):
    list_editable = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dynamically create methods for fields in list_editable if they don't exist
        for field_name in self.list_editable:
            if not hasattr(self, field_name):
                setattr(self, field_name, self._create_ajax_callback(field_name))

    def _create_ajax_callback(self, field_name):
        def render_field(obj):
            val = getattr(obj, field_name) or ""
            model_label = f"{obj._meta.app_label}.{obj._meta.model_name}"
            return format_html(
                '<div class="ajax-section-wrapper relative">'
                '<input type="text" value="{}" '
                'class="section-ajax-input w-full bg-transparent border-b border-gray-300 focus:border-primary-500 outline-none transition-colors py-1" '
                'data-id="{}" data-model="{}" data-field="{}" />'
                '<span class="ajax-status-indicator absolute right-0 top-1 text-[10px] hidden"></span>'
                '</div>',
                val, obj.pk, model_label, field_name
            )
        render_field.short_description = field_name.replace("_", " ").capitalize()
        return render_field



@admin.action(description="Add to comic video")
def comic_to_video(modeladmin, request, queryset):
    for obj in queryset:
        scene_video = SceneVideo.get_from_scene(obj.scene)
        VideoItem.objects.create(
            name=obj.name,
            image= obj.image_comic if obj.image_comic else obj.image,
            scene_video=scene_video,
            order=obj.order,
        )

@admin.action(description="Add to scene video")
def video_to_scene_video(modeladmin, request, queryset):
    for obj in queryset:
        scene_video = SceneVideo.get_from_scene(obj.scene)
        VideoItem.objects.create(
            name=obj.name,
            video= obj.video,
            scene_video=scene_video,
            order=obj.order,
        )


@admin.action(description="Clone selected actions")
def clone(modeladmin, request, queryset):
    for obj in queryset:
        props = None
        extras = None
        many_to_many_count = 0
        if hasattr(obj, 'props'):
            props = obj.props.all()
        if hasattr(obj, 'extras'):
            extras = obj.extras.all()
        obj.pk = None
        if hasattr(obj, 'name'):
            obj.name = f"{obj.name} (Clone)"
        if hasattr(obj, 'order'):
            obj.order = obj.order + 1
        obj.save()
        if props is not None:
            obj.props.set(props)
            many_to_many_count  += obj.props.count() 
        if extras is not None:
            obj.extras.set(extras)
            many_to_many_count  += obj.extras.count()

    modeladmin.message_user(request, "Selected actions have been cloned.")

@admin.action(description="Generate image")
def default_generate_image(modeladmin, request, queryset):
    for obj in queryset:
        if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_IMAGE, owner=request.user) is None:
            obj.generate_image()
        modeladmin.message_user(request, "Image generated for item ID {}.".format(obj.id))

@admin.action(description="Refine image")
def default_refine_image(modeladmin, request, queryset):
    for obj in queryset:
        if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_REFINE_IMAGE, owner=request.user) is None:
            obj.refine_image() 
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
            obj.generate_video(obj.PRESET_VIDEO)
        modeladmin.message_user(request, "video generated for item ID {}.".format(obj.id))

@admin.action(description="Comic from image" )
def generate_comic(modeladmin, request, queryset):
    for obj in queryset:
        if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_COMIC, owner=request.user) is None:
            obj.generate_comic()
        modeladmin.message_user(request, "comic generated for item ID {}.".format(obj.id))

@admin.action(description="Video from first to last")
def generate_video_first_last(modeladmin, request, queryset):
    for obj in queryset:
        if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_VIDEO_FIRST_LAST, owner=request.user) is None:
            obj.generate_video(obj.PRESET_VIDEO_FIRST_LAST, obj)
        modeladmin.message_user(request, "video generated for item ID {}.".format(obj.id))

@admin.action(description="Video from first to last")
def generate_voice(modeladmin, request, queryset):
    for obj in queryset:
        if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_VOICE, owner=request.user) is None:
            obj.generate_voice(obj.PRESET_VOICE, obj)
        modeladmin.message_user(request, "voice generated for item ID {}.".format(obj.id))


class AjaxTaskModelAdmin(ModelAdmin):
    class Media:
        js = ('js/admin_ajax.js',) # We will create this file
        
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'ajax-update/<int:object_id>/',
                self.admin_site.admin_view(self.ajax_update_view),
                name='action_ajax_update',
            ),
            path(
                'ajax-last-tasks/<int:object_id>/',
                self.admin_site.admin_view(self.get_last_tasks),
                name='action_ajax_last_tasks',
            ),
        ]
        return custom_urls + urls

    def get_last_tasks(self, request, object_id):
        # 1. Get the object
        obj = get_object_or_404(self.model, pk=object_id)
    
        return JsonResponse({
            'html': obj.last_tasks(),
        })
    
    def ajax_update_view(self, request, object_id):
        # Implementation of the view logic from step 1
        # Use 'self' instead of passing model_admin
        obj = get_object_or_404(self.model, pk=object_id)
        if request.POST.get('prompt') is not None:
            obj.prompt = request.POST.get('prompt')
            obj.save()
            if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_IMAGE, owner=request.user) is None:
                obj.generate_image()
        elif request.POST.get('prompt_refine') is not None:
            obj.prompt_refine = request.POST.get('prompt_refine')
            obj.save()
            if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_REFINE_IMAGE, owner=request.user) is None:
                obj.refine_image()
        elif request.POST.get('prompt_comic') is not None:
            obj.prompt_comic = request.POST.get('prompt_comic')
            obj.save()
            if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_COMIC, owner=request.user) is None:
                obj.generate_comic()
        elif request.POST.get('prompt_video') is not None:
            obj.prompt_video = request.POST.get('prompt_video')
            obj.save()
            if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_VIDEO, owner=request.user) is None:
                obj.generate_video()
        elif request.POST.get('prompt_voice') is not None:
            obj.prompt_voice = request.POST.get('prompt_voice')
            obj.save()
            if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_VOICE, owner=request.user) is None:
                obj.generate_voice(obj.PRESET_VOICE, request.user)
        return JsonResponse({'status': 'success'})
    
@admin.register(Story)
class StoryAdmin(ModelAdmin):
    list_display = ('name',)
    list_display_links = ('name',)
    search_fields = ['name']

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
class CharacterAdmin(StoryFilterMixin, AjaxTaskModelAdmin, ImgShowMixin,):
    list_display = ('name', 'pic', 'prompt', 'prompt_refine', 'last_tasks')
    list_editable = ('prompt', 'prompt_refine')
    list_display_links = ('name',)
    autocomplete_fields = ['story']
    actions = [clone, default_generate_image, default_refine_image]
    search_fields = ['name']
    fieldsets = ELEMENT_FIELDSETS

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
    list_display = ('name', 'story')
    list_display_links = ('name',)
    autocomplete_fields = ['story',]
    actions = [clone]


@admin.register(Action)
class ActionAdmin(SceneFilterMixin, AjaxTaskModelAdmin, ImgShowMixin):
    list_display = ('id', 'pic', 'prompt','prompt_refine', 'last_tasks')
    list_editable = ( 'prompt', 'prompt_refine')
    list_filter = ["scene", "order"]
    ordering_field = "order"
    hide_ordering_field = True
    list_display_links = ('id',)
    autocomplete_fields = ['actor', 'props', 'extras', 'background', 'consistent_with', 'scene']
    search_fields = ['name']
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

@admin.register(VideoItem)
class VideoItemAdmin(ModelAdmin, ImgShowMixin):
    list_display = ('name', 'video_player', 'pic', 'config', 'order')
    list_editable = ('order', 'config')
    list_display_links = ('name',)

@admin.register(SceneVideo)
class SceneVideoAdmin(ModelAdmin, ImgShowMixin):
    @admin.action(description="Refresh Scene Video" )
    def generate_video(modeladmin, request, queryset):
        for obj in queryset:
            if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_SCENE_VIDEO) is None:
                obj.generate_video(obj.PRESET_VIDEO)
            modeladmin.message_user(request, "video generated for item ID {}.".format(obj.id))

    list_display = ('name', 'scene', 'video_player', 'video_download', 'last_tasks')
    list_display_links = ('name',)
    actions = [generate_video]
