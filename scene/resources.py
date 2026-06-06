import os
import requests
from django.core.files.base import ContentFile
from import_export import resources, fields, widgets
from filer.models.imagemodels import Image as FilerImage
from filer.models.filemodels import File as FilerFile
from .models import Story, Scene, Action, Character, Prop, Background, Voice

class FilerMediaWidget(widgets.ForeignKeyWidget):
    """
    Widget to handle FilerImageField and FilerFileField.
    Exports the absolute URL. 
    On import, downloads the file from the URL and creates a Filer instance.
    """
    def __init__(self, model=FilerImage, *args, **kwargs):
        super().__init__(model, *args, **kwargs)

    def clean(self, value, row=None, **kwargs):
        if not value or not str(value).startswith('http'):
            return super().clean(value, row, **kwargs)

        # Logic to download and create Filer record
        try:
            response = requests.get(value)
            if response.status_code == 200:
                filename = os.path.basename(value)
                file_content = ContentFile(response.content)
                
                # Create the Filer record
                instance = self.model()
                instance.file.save(filename, file_content, save=True)
                instance.name = filename
                instance.save()
                return instance
        except Exception as e:
            print(f"Failed to import media from {value}: {e}")
        return None

    def render(self, value, obj=None):
        if value and hasattr(value, 'url'):
            return value.url
        return ""

class StoryResource(resources.ModelResource):
    class Meta:
        model = Story
        fields = ('id', 'name', 'order', 'style', 'theme', 'group', 'prompt', 'render_type')
        export_order = fields

class CharacterResource(resources.ModelResource):
    image = fields.Field(column_name='image_url', attribute='image', widget=FilerMediaWidget(FilerImage))
    story = fields.Field(column_name='story', attribute='story', widget=widgets.ForeignKeyWidget(Story, 'name'))

    class Meta:
        model = Character
        fields = ('id', 'name', 'prompt', 'image', 'story')

class BackgroundResource(resources.ModelResource):
    image = fields.Field(column_name='image_url', attribute='image', widget=FilerMediaWidget(FilerImage))
    story = fields.Field(column_name='story', attribute='story', widget=widgets.ForeignKeyWidget(Story, 'name'))

    class Meta:
        model = Background
        fields = ('id', 'name', 'prompt', 'image', 'story')

class PropResource(resources.ModelResource):
    image = fields.Field(column_name='image_url', attribute='image', widget=FilerMediaWidget(FilerImage))
    story = fields.Field(column_name='story', attribute='story', widget=widgets.ForeignKeyWidget(Story, 'name'))

    class Meta:
        model = Prop
        fields = ('id', 'name', 'prompt', 'image', 'story')

class SceneResource(resources.ModelResource):
    story = fields.Field(column_name='story', attribute='story', widget=widgets.ForeignKeyWidget(Story, 'name'))

    class Meta:
        model = Scene
        fields = ('id', 'name', 'prompt', 'order', 'story')

class ActionResource(resources.ModelResource):
    scene = fields.Field(column_name='scene', attribute='scene', widget=widgets.ForeignKeyWidget(Scene, 'id'))
    image = fields.Field(column_name='image_url', attribute='image', widget=FilerMediaWidget(FilerImage))
    image_comic = fields.Field(column_name='image_comic_url', attribute='image_comic', widget=FilerMediaWidget(FilerImage))
    video = fields.Field(column_name='video_url', attribute='video', widget=FilerMediaWidget(FilerFile))
    audio_voice = fields.Field(column_name='audio_url', attribute='audio_voice', widget=FilerMediaWidget(FilerFile))
    
    # Foreign Keys for elements
    background = fields.Field(attribute='background', widget=widgets.ForeignKeyWidget(Background, 'name'))
    actor = fields.Field(attribute='actor', widget=widgets.ForeignKeyWidget(Character, 'name'))

    class Meta:
        model = Action
        fields = (
            'id', 'name', 'scene', 'order', 'prompt', 'text', 
            'image', 'image_comic', 'video', 'audio_voice',
            'background', 'actor'
        )