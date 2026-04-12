from django.utils.html import format_html

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
        if obj.voice:
            return format_html('''
        <audio controls>
            <source src="{}" type="audio/mpeg">
        </audio>
        ''', obj.voice.url)
        return "No contents"
