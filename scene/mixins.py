from django.utils.html import format_html

ELEMENT_FIELDSETS = (
        ("Write", {
            "classes": ["tab"],
            "fields": ["prompt", 'action'],
        }),
        ("Settings", {
            "classes": ["tab"],
            "fields": ["prompt_refine", "story", ],
        }),
    )

ACTION_FIELDSETS = (
        ("Composition", {
            "classes": ["tab"],
            "fields": ["name", "scene", "prompt","order", "actor", "props", "extras", "background", "consistent_with",  "image"],
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
            "fields": ["exec_on_save"],
        }),
    )

class ImgShowMixin:
    MAX_IMAGE_HEIGHT = 400

    def video_download(self, obj):
        if obj.video:
            return format_html('<a href="{}" download >Download</a>', obj.video.url)
        return "No Video"

    def pic(self, obj):
        if obj.image:
            return format_html('<a href="{}" download ><img src="{}" style="max-height: {}px;" /></a>', obj.image.url, obj.image.url, self.MAX_IMAGE_HEIGHT)
        return "No Image"

    def pic_comic(self, obj):
        if obj.image_comic:
            return format_html('<a href="{}" download ><img src="{}" style="max-height: {}px;" /></a>', obj.image_comic.url, obj.image_comic.url, self.MAX_IMAGE_HEIGHT)
        return "No Image"
    
    def pic_refine(self, obj):
        if obj.image_refine:
            return format_html('<a href="{}" download ><img src="{}" style="max-height: {}px;" /></a>', obj.image_refine.url, obj.image_refine.url, self.MAX_IMAGE_HEIGHT)
        return "No Image"
    
    def pic_first(self, obj):
        if obj.image_first:
            return format_html('<a href="{}" download ><img src="{}" style="max-height: {}px;" /></a>', obj.image_first.url, obj.image_first.url, self.MAX_IMAGE_HEIGHT)
        return "No Image"
    
    def pic_last(self, obj):
        if obj.image_last:
            return format_html('<a href="{}" download ><img src="{}" style="max-height: {}px;" /></a>', obj.image_last.url, obj.image_last.url, self.MAX_IMAGE_HEIGHT)
        return "No Image"

    def action_pic(self, obj):
        if obj.action.image:
            return format_html('<img src="{}" style="max-height: {}px;" />', obj.action.image.url, self.MAX_IMAGE_HEIGHT)
        return "No Image"
    
    def contents(self, obj):

        if obj.get_contents():
            return format_html('''                               
        <a class="btn btn-primary" data-toggle="collapse" href="#collapse{}" role="button" aria-expanded="false" aria-controls="collapseExample">
            Get Prompt
        </a>
        <div class="collapse" id="collapse{}">
            <div class="card card-body">
                {}
            </div>
        </div>
        {}
        ''', obj.id, obj.id, obj.get_contents(), obj.features() if hasattr(obj, 'features') else "")
        return "No contents"
    
    def contents_refine(self, obj):
        if obj.get_contents(generate_self=True, preset=obj.PRESET_REFINE):
            return format_html('''
        <a class="btn btn-primary" data-toggle="collapse" href="#collapse{}" role="button" aria-expanded="false" aria-controls="collapseExample">
            Get Prompt
        </a>
        <div class="collapse" id="collapse{}">
            <div class="card card-body">
                {}
            </div>
        </div>
        ''', obj.id, obj.id, obj.get_contents(generate_self=True, preset=obj.PRESET_REFINE))
        return "No contents"

    def video_player(self, obj):
        if obj.video:
            return format_html('''
        <video height="500" controls>
            <source src="{}" type="video/mp4">
        </video>
        ''', obj.video.url)
        return "No contents"
    
    def voice_player(self, obj):
        if obj.audio_voice:
            return format_html('''
        <audio controls>
            <source src="{}" type="audio/mpeg">
        </audio>
        ''', obj.audio_voice.url)
        return "No contents"

class SceneFilterMixin:
    # anything that has a scene foreign key can use this mixin to filter by the user's current scene

    def save_model(self, request, obj, form, change):
        if obj.scene is None and request.user.story_profile.scene:
            obj.scene = request.user.story_user.scene
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