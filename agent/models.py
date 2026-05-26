from google import genai
import random
import os
import time
import instructor
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils.module_loading import import_string

from django.contrib.contenttypes.models import ContentType
from django.db import models
from agent.utils import wave_file
from PIL import Image
from io import BytesIO
from filer.fields.image import FilerImageField
from filer.fields.file import FilerFileField
from filer.models.imagemodels import Image as FilerImage
from django.utils.text import slugify
from easy_thumbnails.files import get_thumbnailer

from task.models import Task
from PIL import Image



class GetContentsMixin:
    PRESET_REFINE = "refine"
    PRESET_VIDEO = "video_image"
    PRESET_VIDEO_FIRST_LAST = "video_first_last"
    PRESET_COMIC = "comic"
    PRESET_VOICE = "voice"
    PRESET_CHARACTER = "character"
    PRESET_WRITER = "writer"
    PRESET_REFINE_PROMPT = "refine_prompt"
    PRESET_SCENE = "generate_scene"
    

    @property
    def messages(self):
        return Message.objects.filter(
            content_type=ContentType.objects.get_for_model(self.__class__),
            object_id=self.pk
        ).order_by('created_at')

    def get_contents(self, generate_self=True, preset=None):
         # remove generate self and add preset regenerate_image
        parts = [self.context_text(generate_self=generate_self, preset=preset)]
        if not generate_self or preset in [self.PRESET_REFINE, self.PRESET_COMIC]:
            if hasattr(self, 'image') and self.image:
                parts.append(self.get_thumbnail(preset=preset))
        return parts
    
    def get_thumbnail(self, preset=None):
        if self.image:
            # half the size to make it cheaper
            try:
                thumbnail = get_thumbnailer(self.image.file).get_thumbnail({'size': (0, self.image.height/2)})
                return Image.open(thumbnail.path)
            except Exception as e:
                print(f"Error occurred while generating thumbnail: {e}")
        return None
    
    def generate_image(self, user=None):
        agent = Agent.objects.filter(output_type=Agent.OUTPUT_TYPE_IMAGE).first()
        self.image = agent.generate(self, user=user, target_field="image")
        self.save()
        return self.image
    
    def refine_image(self, save=True, user=None):
        image_agent = Agent.objects.filter(output_type=Agent.OUTPUT_TYPE_IMAGE).first()
        out = image_agent.generate(self, preset=self.PRESET_REFINE, user=user, target_field="image")
        if save and out:
            self.image = out
            self.save()
        return out
    
    def generate_video(self, preset, user=None):
        agent = Agent.objects.filter(output_type=Agent.OUTPUT_TYPE_VIDEO).first()
        self.video = agent.generate(self, preset=preset, user=user, target_field="video")
        self.save()
        return self.video

    def generate_voice(self, preset, user=None):
        agent = Agent.objects.filter(output_type=Agent.OUTPUT_TYPE_VOICE).first()
        self.voice = agent.generate(self, preset=preset, user=user, target_field="voice")
        self.save()
        return self.voice
    
    def generate_scene(self, preset=PRESET_SCENE, user=None):
        agent = Agent.objects.filter(schema=settings.SCHEMA_MULTI_SCENE).first()
        scene = agent.generate(self, preset=preset, user=user, target_field="scene")
        self.scene = scene
        self.save()
        return self.scene

    def refine_image(self, save=True, user=None):
        image_agent = Agent.objects.filter(output_type=Agent.OUTPUT_TYPE_IMAGE).first()
        out = image_agent.generate(self, preset=self.PRESET_REFINE_PROMPT, user=user, target_field="image")
        if save and out:
            self.image = out
            self.save()
        return out
    
    def refine_prompt(self, save=True, user=None, agent=None):
        if agent is None:
            text_agent = Agent.objects.filter(output_type=Agent.OUTPUT_TYPE_TEXT).first()
        out = text_agent.generate(self, preset=self.PRESET_REFINE, user=user, target_field="prompt")
        if save and out:
            self.image = out
            self.save()
        return out

class AgentModel(models.Model):
    name = models.CharField(max_length=100, default="name")
    def __str__(self):
        return "{}".format(self.name)

class Voice(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=100)

    def __str__(self):
        return "{}".format(self.name)

class Prompt(models.Model):
    CHOICES = (
        ("general", "General"),
        (GetContentsMixin.PRESET_REFINE, "Refine"),
        (GetContentsMixin.PRESET_VIDEO, "Video"),
        (GetContentsMixin.PRESET_VIDEO_FIRST_LAST, "Video First Last"),
        (GetContentsMixin.PRESET_COMIC, "Comic"),
        (GetContentsMixin.PRESET_WRITER, "Writer"),
        (GetContentsMixin.PRESET_CHARACTER, "Character"),
        (GetContentsMixin.PRESET_REFINE_PROMPT, "Refine Prompt"),
        (GetContentsMixin.PRESET_SCENE, "Sync Scene"),
        
    )
    name= models.CharField(max_length=100, default="name")
    prompt = models.TextField(null=True, blank=True)
    category = models.CharField(max_length=100, default="general", choices=CHOICES)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)

    @classmethod
    def instructions(cls, preset, obj):
        from_preset =  [item.prompt for item in cls.objects.filter(category=preset) ]
        content_type = ContentType.objects.get_for_model(obj.__class__)
        from_content = [item.prompt for item in cls.objects.filter(content_type=content_type)]
        out = from_preset + from_content
        return out

    @classmethod
    def prompt_for_model(cls, obj):
        content_type = ContentType.objects.get_for_model(obj.__class__)
        from_content = [item.prompt for item in cls.objects.filter(content_type=content_type)]
        return from_content

    def __str__(self):
        return "{}".format(self.name)
    
class Agent(models.Model):
    OUTPUT_TYPE_IMAGE = "image"
    OUTPUT_TYPE_TEXT = "text"
    OUTPUT_TYPE_VOICE = "voice"
    
    OUTPUT_TYPE_STRUCTURED = "structured"
    OUTPUT_TYPE_VIDEO = "video"

    
    name = models.CharField(max_length=100, default="name")
    instructions = models.ManyToManyField("Prompt", related_name='agents', blank=True)
    agent_model = models.ForeignKey(AgentModel, related_name='agents', on_delete=models.CASCADE)
    output_type = models.CharField(
        max_length=100,
        default=OUTPUT_TYPE_TEXT,
        choices=getattr(settings, "AGENT_OUTPUT_TYPE_CHOICES", [
            (OUTPUT_TYPE_IMAGE, "Image"),
            (OUTPUT_TYPE_TEXT, "Text"),
            (OUTPUT_TYPE_STRUCTURED, "Structured"),
            (OUTPUT_TYPE_VIDEO, "Video"),
            (OUTPUT_TYPE_VOICE, "Voice"),
        ])
    )
    schema = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        choices=settings.AGENT_SCHEMA_CHOICES
    )

    def get_schema_class(self):
        schema_path = settings.AGENT_SCHEMAS.get(self.schema)
        return import_string(schema_path) if schema_path else None

    def get_genai_client(self, user):
        if user and hasattr(user, 'agent_profile') and user.agent_profile.google_api_key:
            api_key = user.agent_profile.google_api_key.api_key
            genai_client = genai.Client(
                vertexai=True,
                api_key=api_key
            )
            return genai_client
        else:
            raise Exception("User does not have an API key configured. Please set up your API key in your profile settings.")

    def save_usage(self, user, response):
        usage = response.usage_metadata
        usage_dict = {
            "prompt_token_count": str(usage.prompt_token_count),
            "candidates_token_count": str(usage.candidates_token_count),
            "total_token_count": str(usage.total_token_count),
            "api_key_id": user.agent_profile.google_api_key.id,
            
            # Fields for advanced features (if available)
        }
        TokenUsage.objects.create(
            user=user,
            json_report=usage_dict,
            tokens= usage_dict.get("total_token_count", 0),
        )

    def get_instructor(self, user=None):
        out = instructor.from_genai(
            self.get_genai_client(user),
            mode=instructor.Mode.GENAI_STRUCTURED_OUTPUTS,
            use_async=True,
        )
        return out

    def __str__(self):
        return "{}".format(self.name)
    
    def generate_text(self, response, prompt_obj):
        try:
            return response.text
        except ValueError:
            if response.candidates:
                return f"Response blocked. Finish reason: {response.candidates[0].finish_reason}"
            return "No text was generated."

    def generate_voice(self, preset, prompt_obj, user=None):
        # Check for errors if voice is not generated
        from google.genai import types

        out = None
        client = self.get_genai_client(user)
        contents = prompt_obj.get_contents(generate_self=True, preset=preset)
        response = client.models.generate_content(
            model=self.agent_model.name,
            contents=contents['prompt'],
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=contents['voice'],
                        )
                    )
                ),
            )
        )
        data = response.candidates[0].content.parts[0].inline_data.data
        self.save_usage(user, response)
        name = f"voice_{slugify(prompt_obj.__class__.__name__)}_{slugify(prompt_obj.name)}_{slugify(self.name)}_{random.randint(1000,9999)}.wav"
        filepath_relative = f"agent_voices/{name}"
        filepath_abs = os.path.join( settings.MEDIA_ROOT, filepath_relative)
        wave_file(filepath_abs, data)
        out = FilerImage.objects.create(
            original_filename=name,
            file=filepath_relative,
            name=name
        )
        return out

    def generate_video(self, preset, prompt_obj, user=None):
        # Check for errors if a video is not generated
        from google.genai import types
        out = None
        client = self.get_genai_client(user)
        contents = prompt_obj.get_contents(generate_self=True, preset=preset)
        if preset == GetContentsMixin.PRESET_VIDEO:
            operation = client.models.generate_videos(
                model=self.agent_model.name,
                prompt=contents['prompt'],
                image=contents['image'] if 'image' in contents else None
            )
        elif preset == GetContentsMixin.PRESET_VIDEO_FIRST_LAST:
            operation = client.models.generate_videos(
                model=self.agent_model.name,
                prompt=contents['prompt'],
                image=contents['image_first'] if 'image_first' in contents else None,
                config=types.GenerateVideosConfig(
                    last_frame=contents['image_last'] if 'image_last' in contents else None
                ),
            )
        # Poll the operation status until the video is ready.
        while not operation.done:
            print("Waiting for video generation to complete...")
            time.sleep(5)
            operation = client.operations.get(operation)
        # Download the generated video.
        if operation.response.generated_videos is None:
            raise Exception(operation.response.rai_media_filtered_reasons)
        generated_video = operation.response.generated_videos[0]
        self.save_usage(user, operation.response)

        name = f"video_{slugify(prompt_obj.__class__.__name__)}_{slugify(prompt_obj.name)}_{slugify(self.name)}_{random.randint(1000,9999)}.mp4"
        filepath_relative = f"agent_videos/{name}"
        filepath_abs = os.path.join( settings.MEDIA_ROOT, filepath_relative)
        generated_video.video.save(filepath_abs)
        out = FilerImage.objects.create(
            original_filename=name,
            file=filepath_relative,
            name=name
        )
        return out

    def save_image(self, response, prompt_obj):
        # Check for errors if an image is not generated
        out = None
        from google.genai.types import FinishReason
        if response.candidates[0].finish_reason != FinishReason.STOP:
            reason = response.candidates[0].finish_reason
            raise ValueError(f"Prompt Content Error: {reason}")
        
        for part in response.candidates[0].content.parts:
            if part.inline_data:
                image_data = BytesIO(part.inline_data.data)
                out =  Image.open(image_data)
                name = f"{slugify(prompt_obj.__class__.__name__)}_{slugify(prompt_obj.name)}_{slugify(self.name)}_{random.randint(1000,9999)}"
                filepath_relative = f"agent_images/{name}.png"
                filepath_abs = os.path.join( settings.MEDIA_ROOT, filepath_relative)
                out.save(filepath_abs, format="PNG")
                out = FilerImage.objects.create(
                    original_filename=name,
                    file=filepath_relative,
                    name=name
                )
        return out
    
    def get_instructions(self, user=None, preset=None, obj=None):
        instructions = [ item.prompt for item in self.instructions.all()]
        if preset:
            instructions += Prompt.instructions(preset, obj)
        return instructions
    
    def generate(self, obj, preset=None, user=None, target_field=None):
        from google.genai import types
        # Placeholder for agent generation logic
        contents = obj.get_contents(generate_self=True, preset=preset)
        config = None
        out = None
        # video has  a different config and response handling so handle it separately
        if self.output_type == self.OUTPUT_TYPE_VIDEO:
            out = self.generate_video(preset, obj, user=user)
        if self.output_type == self.OUTPUT_TYPE_VOICE:
            out = self.generate_voice(preset, obj, user=user)
        else:
            if self.output_type == self.OUTPUT_TYPE_STRUCTURED:
                schema_class = self.get_schema_class()
                config = types.GenerateContentConfig(
                    system_instruction=self.get_instructions(user=user, preset=preset, obj=obj),
                    response_mime_type="application/json" if schema_class else None,
                    response_schema=schema_class,
                    temperature=0.1,
                )
            elif self.output_type == self.OUTPUT_TYPE_IMAGE:
                config = types.GenerateContentConfig(
                    image_config=types.ImageConfig(
                        aspect_ratio="9:16",
                    )
                )
            elif self.output_type in self.OUTPUT_TYPE_TEXT:
                config = types.GenerateContentConfig(
                    system_instruction= self.get_instructions(user=user, preset=preset, obj=obj)
                )
        
            with self.get_genai_client(user) as client:
                response = client.models.generate_content(
                    model=self.agent_model.name,
                    contents=contents,
                    config=config
                )
                out = None
                self.save_usage(user, response)
                if self.output_type == self.OUTPUT_TYPE_TEXT:
                    out =  self.generate_text(response, obj)
                elif self.output_type == self.OUTPUT_TYPE_IMAGE:
                    out = self.save_image(response, obj)
                elif self.output_type == self.OUTPUT_TYPE_STRUCTURED:
                    schema_class = self.get_schema_class()
                    if schema_class:
                        data = schema_class.model_validate_json(response.text)
                        out = data.sync_model(obj) if hasattr(data, "sync_model") else data

        Message.objects.create(
            content_object=obj,
            agent=self,
            user=user, # Add the user here
            input_text=str(contents),
            output_text=out if self.output_type == self.OUTPUT_TYPE_TEXT else "",
            output_image=out if self.output_type == self.OUTPUT_TYPE_IMAGE else None,
            output_file=out if self.output_type in [self.OUTPUT_TYPE_VIDEO, self.OUTPUT_TYPE_VOICE] else None,
            target_field=target_field or ""
        )

        return out


class TokenUsage(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    agent = models.ForeignKey(Agent, related_name='token_usages', on_delete=models.SET_NULL, null=True, blank=True)
    task = models.ForeignKey(Task, related_name='token_usages', on_delete=models.SET_NULL, null=True, blank=True)
    tokens = models.PositiveIntegerField(default=0)
    json_report = models.JSONField(null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='token_usages', on_delete=models.SET_NULL, null=True, blank=True)

class GoogleApiKey(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='api_keys', on_delete=models.CASCADE)
    name = models.CharField(unique=True, max_length=255, null=True, blank=True)
    api_key = models.TextField(null=True, blank=True)
         
    def __str__(self):
        return "{}-{}".format(self.name, self.user.username)

class AgentProfile(models.Model):

    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name='agent_profile', on_delete=models.CASCADE)
    credits = models.PositiveIntegerField(default=0)
    google_api_key = models.ForeignKey(GoogleApiKey, related_name='agent_profiles', on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = 'AI User Profile'
        verbose_name_plural = 'AI User Profiles'

    def __str__(self):
        return "{}".format(self.user.username)

class Message(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    agent = models.ForeignKey(Agent, on_delete=models.SET_NULL, null=True, blank=True, related_name='chat_history')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='agent_messages')
    input_text = models.TextField(blank=True)
    output_text = models.TextField(blank=True)
    output_image = FilerImageField(null=True, blank=True, on_delete=models.SET_NULL, related_name='message_images')
    output_file = FilerFileField(null=True, blank=True, on_delete=models.SET_NULL, related_name='message_files')
    target_field = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']