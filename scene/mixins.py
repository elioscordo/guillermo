from django.contrib import admin
from django.utils.html import format_html

from django.utils.translation import gettext_lazy as _
from django.urls import path
from django.conf import settings
from task.models import Task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.contrib.auth.models import Group, Permission, User
from django.conf import settings
import secrets
import string
from django.http import JsonResponse
from django.apps import apps
from django.shortcuts import get_object_or_404

ELEMENT_FIELDSETS = (
        ("Write", {
            "classes": ["tab"],
            "fields": ["name","prompt",  'action'],
        }),
        ("Settings", {
            "classes": ["tab"],
            "fields": ["image","prompt_refine", "story" ],
        }),
    )

ACTION_FIELDSETS = (
        ("Composition", {
            "classes": ["tab"],
            "fields": ["name", "scene", "prompt","order", "actor", "props", "cast", "background", "consistent_with",  "image"],
        }),
        ("Video", {
            "classes": ["tab"],
            "fields": ["prompt_video", "video", "image_first", "image_last"],
        }),
        ("Refine", {
            "classes": ["tab"],
            "fields": ["prompt_refine", "image_refine"],
        }),
        ("Execute On Save", {
            "classes": ["tab"],
            "fields": ["action"],
        }),
    )

class ModelDisplayMixin:
    MAX_IMAGE_HEIGHT = 400

    def video_download(self):
        video = getattr(self, 'video', None)
        if video:
            return format_html('<a href="{}" download >{}</a>', video.url, _("Download"))
        return _("No Video")
    video_download.short_description = _("Video Download")

    def pic(self):
        image = getattr(self, 'image', None)
        if image:
            return format_html('<a href="{}" download ><img src="{}" style="max-height: {}px;" /></a>', image.url, image.url, self.MAX_IMAGE_HEIGHT)
        return _("No Image")
    pic.short_description = _("Image")

    def pic_comic(self):
        image_comic = getattr(self, 'image_comic', None)
        if image_comic:
            return format_html('<a href="{}" download ><img src="{}" style="max-height: {}px;" /></a>', image_comic.url, image_comic.url, self.MAX_IMAGE_HEIGHT)
        return _("No Image")
    pic_comic.short_description = _("Comic Image")
    
    def pic_refine(self):
        image_refine = getattr(self, 'image_refine', None)
        if image_refine:
            return format_html('<a href="{}" download ><img src="{}" style="max-height: {}px;" /></a>', image_refine.url, image_refine.url, self.MAX_IMAGE_HEIGHT)
        return _("No Image")
    pic_refine.short_description = _("Refined Image")
    
    def pic_first(self):
        image_first = getattr(self, 'image_first', None)
        if image_first:
            return format_html('<a href="{}" download ><img src="{}" style="max-height: {}px;" /></a>', image_first.url, image_first.url, self.MAX_IMAGE_HEIGHT)
        return _("No Image")
    pic_first.short_description = _("First Frame")
    
    def pic_last(self):
        image_last = getattr(self, 'image_last', None)
        if image_last:
            return format_html('<a href="{}" download ><img src="{}" style="max-height: {}px;" /></a>', image_last.url, image_last.url, self.MAX_IMAGE_HEIGHT)
        return _("No Image")
    pic_last.short_description = _("Last Frame")

    def action_pic(self):
        action = getattr(self, 'action', None)
        if action and hasattr(action, 'image') and action.image:
             return format_html('<img src="{}" style="max-height: {}px;" />', action.image.url, self.MAX_IMAGE_HEIGHT)
        return _("No Image")
    action_pic.short_description = _("Action Image")
    
    def contents_html(self):
        if hasattr(self, 'get_contents') and self.get_contents():
            return format_html('''
        <a class="btn btn-primary" data-toggle="collapse" href="#collapse{}" role="button" aria-expanded="false" aria-controls="collapseExample">
            {}
        </a>
        <div class="collapse" id="collapse{}">
            <div class="card card-body">
                {}
            </div>
        </div>
        {}
        ''', self.id, _("Get Prompt"), self.id, self.get_contents(), self.features() if hasattr(self, 'features') else "")
        return _("No contents")
    contents_html.short_description = _("Contents")
    
    def contents_refine_html(self):
        if hasattr(self, 'get_contents') and hasattr(self, 'PRESET_REFINE') and self.get_contents(generate_self=True, preset=self.PRESET_REFINE):
            return format_html('''
        <a class="btn btn-primary" data-toggle="collapse" href="#collapse{}" role="button" aria-expanded="false" aria-controls="collapseExample">
            {}
        </a>
        <div class="collapse" id="collapse{}">
            <div class="card card-body">
                {}
            </div>
        </div>
        ''', self.id, _("Get Prompt"), self.id, self.get_contents(generate_self=True, preset=self.PRESET_REFINE))
        return _("No contents")
    contents_refine_html.short_description = _("Refined Contents")

    def video_player(self):
        video = getattr(self, 'video', None)
        if video:
            return format_html('''
        <video height="500" controls>
            <source src="{}" type="video/mp4">
        </video>
        ''', video.url)
        return _("No contents")
    video_player.short_description = _("Video Player")
    
    def voice_player(self):
        audio_voice = getattr(self, 'audio_voice', None)
        if audio_voice:
            return format_html('''
        <audio controls>
            <source src="{}" type="audio/mpeg">
        </audio>
        ''', audio_voice.url)
        return _("No contents")
    voice_player.short_description = _("Voice Player")

class SceneFilterMixin:
    # anything that has a scene foreign key can use this mixin to filter by the user's current scene

    def save_model(self, request, obj, form, change):
        if hasattr(self, 'scene') and obj.scene is None and request.user.story_profile.scene:
            obj.scene = request.user.story_profile.scene
        save_obj = super().save_model(request, obj, form, change)
        return save_obj

    def get_queryset(self, request):
        qs = super().get_queryset(request) #call original queryset method that you are overriding
        if request.user.story_profile.enable_filters:
            if request.user.story_profile.scene:
                return qs.filter(scene=request.user.story_profile.scene)
            return qs.filter(scene__story=request.user.story_profile.get_current_story())
        return qs

class StoryFilterMixin:
    # anything that has a story foreign key can use this mixin to filter by the user's current scene
    
    def save_model(self, request, obj, form, change):
        if obj.story is None:
            obj.story = request.user.story_profile.get_current_story()
        save_obj = super().save_model(request, obj, form, change)
        return save_obj

    def get_queryset(self, request):
        qs = super().get_queryset(request) #call original queryset method that you are overriding
        profile = request.user.story_profile
        if profile.enable_filters:
            return qs.filter(story=profile.get_current_story())
        return qs

class StaffReadOnlyMixin:
    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            readonly_fields.extend(self.staff_readonly_fields)         
        return readonly_fields

class ViewYourOwnMixin:
    def get_queryset(self, request):
        qs = super().get_queryset(request) #call original queryset method that you are overriding
        if not request.user.is_superuser:
            return qs.filter(user=request.user)
        return qs

class EmailSenderMixin: 
    
    def send_email(self, subject,  context, recipient_list):
        html_message = render_to_string(self.email_template, context)
        plain_message = strip_tags(html_message)
        send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            recipient_list,
            html_message=html_message
        )

class UserCreatorMixin:
    
    def create_user(self, obj, email):
        username = email.split('@')[0]
        # 1. Generate a secure random string
        alphabet = string.ascii_letters + string.digits
        password = ''.join(secrets.choice(alphabet) for i in range(12))
        user, created = User.objects.get_or_create(username=username, email=email)
        user.set_password(password)
        user.is_staff = True
        group = Group.objects.get(name='faf')
        user.groups.add(group)
        user.save()
        # Render HTML and create plain text alternative
        html_message = render_to_string(
            'email/invitation.html', 
            {'user': user, 
                'obj': obj,
                'password': password, 
                'cta': settings.SITE_URL + f'/admin/scene/story/?id__exact={obj.id}'
            }
        )
        plain_message = strip_tags(html_message)
        send_mail(
            f'Invitation to co-author: {obj.name}', plain_message, settings.DEFAULT_FROM_EMAIL, [email],
            html_message=html_message # <--- HTML added here
        )
        return user

class PromptPreviewMixin:
    """Mixin to provide an endpoint for previewing prompts based on presets."""
    def get_urls(self):
        return [
            path(
                'prompt-preview/<int:object_id>/',
                self.admin_site.admin_view(self.prompt_preview_view),
                name='prompt_preview',
            ),
        ] + super().get_urls()

    def prompt_preview_view(self, request, object_id):
        obj = get_object_or_404(self.model, pk=object_id)
        preset = request.GET.get('preset') or None
        contents = obj.get_contents(preset=preset)
        
        if isinstance(contents, list):
            # Join string parts with double newlines for readability
            text = "\n\n".join([str(p) for p in contents if isinstance(p, (str, bytes))])
        elif isinstance(contents, dict):
            text = contents.get('prompt', '')
        else:
            text = str(contents)

        return JsonResponse({"content": text})

class AdminActionsMixin:
    @admin.action(description="Add to comic video")
    def comic_to_video(self, request, queryset):
        Render = apps.get_model('scene', 'Render')
        RenderItem = apps.get_model('scene', 'RenderItem')
        for obj in queryset:
            render = Render.get_from_scene(obj.scene)
            RenderItem.objects.create(
                image= obj.image_comic if obj.image_comic else obj.image,
                render=render,
                order=obj.order,
            )

    @admin.action(description="Add to scene video")
    def video_to_scene_video(self, request, queryset):
        Render = apps.get_model('scene', 'Render')
        RenderItem = apps.get_model('scene', 'RenderItem')
        for obj in queryset:
            render = Render.get_from_scene(obj.scene)
            RenderItem.objects.create(
                video= obj.video,
                render=render,
                order=obj.order,
            )

    @admin.action(description="Clone selected items")
    def clone(self, request, queryset):
        for obj in queryset:
            props = None
            cast = None
            if hasattr(obj, 'props'):
                props = list(obj.props.all())
            if hasattr(obj, 'cast'):
                cast = list(obj.cast.all())
            obj.pk = None
            if hasattr(obj, 'name') and obj.name:
                obj.name = f"{obj.name} (Clone)"
            if hasattr(obj, 'order'):
                obj.order = obj.order + 1
            obj.save()
            if props is not None:
                obj.props.set(props)
            if cast is not None:
                obj.cast.set(cast)
        self.message_user(request, "Selected items have been cloned.")

    @admin.action(description="Generate image")
    def default_generate_image(self, request, queryset):
        for obj in queryset:
            if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_IMAGE, owner=request.user) is None:
                obj.generate_image(user=request.user)
            self.message_user(request, "Image generated for item ID {}.".format(obj.id))

    @admin.action(description="Refine image")
    def default_refine_image(self, request, queryset):
        for obj in queryset:
            if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_REFINE_IMAGE, owner=request.user) is None:
                obj.refine_image(user=request.user) 
            self.message_user(request, "Image generated for item ID {}.".format(obj.id))

    @admin.action(description="Refined as image")
    def accept_refined_image(self, request, queryset):
        for obj in queryset:
            obj.image=obj.image_refine
            obj.save()
            self.message_user(request, "image accepted for item ID {}.".format(obj.id))

    @admin.action(description="Refined as first frame")
    def accept_refined_first(self, request, queryset):
        for obj in queryset:
            obj.image_first=obj.image_refine
            obj.save()
            self.message_user(request, "image accepted for item ID {}.".format(obj.id))

    @admin.action(description="Refined as last frame")
    def accept_refined_last(self, request, queryset):
        for obj in queryset:
            obj.image_last=obj.image_refine
            obj.save()
            self.message_user(request, "image accepted for item ID {}.".format(obj.id))

    @admin.action(description="Video from image" )
    def generate_video(self, request, queryset):
        for obj in queryset:
            if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_VIDEO, owner=request.user) is None:
                obj.generate_video(obj.PRESET_VIDEO, user=request.user)
            self.message_user(request, "video generated for item ID {}.".format(obj.id))

    @admin.action(description="Comic from image" )
    def generate_comic(self, request, queryset):
        for obj in queryset:
            if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_COMIC, owner=request.user) is None:
                obj.generate_comic(user=request.user)
            self.message_user(request, "comic generated for item ID {}.".format(obj.id))

    @admin.action(description="Video from first to last")
    def generate_video_first_last(self, request, queryset):
        for obj in queryset:
            if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_VIDEO_FIRST_LAST, owner=request.user) is None:
                obj.generate_video(obj.PRESET_VIDEO_FIRST_LAST, user=request.user)
            self.message_user(request, "video generated for item ID {}.".format(obj.id))

    @admin.action(description="Generate Voice")
    def generate_voice(self, request, queryset):
        for obj in queryset:
            if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_VOICE, owner=request.user) is None:
                obj.generate_voice(obj.PRESET_VOICE, user=request.user)
            self.message_user(request, "voice generated for item ID {}.".format(obj.id))

    @admin.action(description="Generate Elements Images (step 2)")
    def generate_scene_elements(self, request, queryset):
        for obj in queryset:
            if Task.createTaskIfQueueEnabled(obj, settings.TASK_TYPE_GENERATE_SCENE_ELEMENTS, owner=request.user) is None:
                pass
            self.message_user(request, "Generation task for elements started for scene: {}.".format(obj.name))

    @admin.action(description="Generate Actions Images (step 3)")
    def generate_scene_actions(self, request, queryset):
        for obj in queryset:
            if Task.createTaskIfQueueEnabled(obj, settings.TASK_TYPE_GENERATE_SCENE_ACTIONS, owner=request.user) is None:
                pass
            self.message_user(request, "Generation task for actions started for scene: {}.".format(obj.name))

    @admin.action(description="Add me as author")
    def add_me_as_author(self, request, queryset):
        for obj in queryset:
            if obj.add_author(request.user):
                self.message_user(request, f"You have been added as an author to story {obj.name}")

    @admin.action(description="Generate Structure (step 1)" )
    def extract_scene(self, request, queryset):
        for obj in queryset:
            if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_EXTRACT_SCENE, owner=request.user) is None:
                obj.generate_scene(user=request.user)
            self.message_user(request, f"Extracting scene from contribution {obj.id} in story {obj.story.id}.")

    @admin.action(description="Generate Render Preview (step 3.5)")
    def generate_render(self, request, queryset):
        for obj in queryset:
            if hasattr(obj, 'generate_render'):
                obj.generate_render()
                self.message_user(request, _("Render generated for scene: {}").format(obj.name))

    @admin.action(description="Refresh Render (step 4)" )
    def refresh_render(self, request, queryset):
        Scene = apps.get_model('scene', 'Scene')
        for obj in queryset:
            if isinstance(obj, Scene):
                render = obj.generate_render()
                Task.createTaskIfQueueEnabled(
                    subject=render,
                    task_type=settings.TASK_TYPE_GENERATE_SCENE_VIDEO,
                    thr=obj,
                    owner=request.user
                )
                self.message_user(request, _("Render generated and video task queued for scene: {}").format(obj.name))
            else:
                if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_VIDEO, owner=request.user) is None:
                    obj.generate_video(obj.PRESET_VIDEO, user=request.user)
                self.message_user(request, "video generated for item ID {}.".format(obj.id))

class RenderTypeMixin:
    RENDER_TYPE_FILM = 'film'
    RENDER_TYPE_GRAPHIC_NOVEL = 'comic'
    RENDER_TYPE_ANIMATIC = 'animatic'

    RENDER_TYPE_CHOICES = [
        (RENDER_TYPE_FILM, 'Film'),
        (RENDER_TYPE_GRAPHIC_NOVEL, 'Graphic Novel'),
        (RENDER_TYPE_ANIMATIC, 'Animatic'),
    ]
    def __getattr__(self, name):
        if name == "is_comic":
            return getattr(self, "render_type", None) == getattr(self, "RENDER_TYPE_GRAPHIC_NOVEL", "comic")
        if name == "is_film":
            return getattr(self, "render_type", None) == getattr(self, "RENDER_TYPE_FILM", "film")
        if name == "is_animatic":
            return getattr(self, "render_type", None) == getattr(self, "RENDER_TYPE_ANIMATIC", "animatic")
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
