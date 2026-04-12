from task.models import Task
from agent.models import GetContentsMixin
from moviepy import ImageClip, VideoFileClip, concatenate_videoclips
from moviepy.video.fx import Resize
import random
from django.utils.text import slugify
import os 
from django.conf import settings
from filer.models.imagemodels import Image as FilerImage

class TaskGenerateImage:
    
    def __init__(self, task):
        self.task = task

    def process(self):
        self.task.set_status(Task.TASK_STATUS_STARTED)
        item = self.task.subject
        item.generate_image(user=self.task.owner)
        self.task.set_status(Task.TASK_STATUS_SUCCESS)


class TaskRefineImage:
    
    def __init__(self, task):
        self.task = task
        
    def process(self):
        item = self.task.subject
        old_image = item.image.url
        item.refine_image(user=self.task.owner)
        image = item.image.url
        print(f"Refined image for item ID {item.id} from {old_image} to {image}")

class TaskGenerateVideo:
    def __init__(self, task):
        self.task = task
    def process(self):
        item = self.task.subject
        item.generate_video(GetContentsMixin.PRESET_VIDEO, user=self.task.owner)

class TaskGenerateVoice:
    def __init__(self, task):
        self.task = task
    def process(self):
        item = self.task.subject
        item.generate_voice(GetContentsMixin.PRESET_VOICE, user=self.task.owner)

class TaskGenerateVideoFirstLast:
    def __init__(self, task):
        self.task = task
    def process(self):
        item = self.task.subject
        item.generate_video(GetContentsMixin.PRESET_VIDEO_FIRST_LAST, user=self.task.owner)

class TaskGenerateComic:
    def __init__(self, task):
        self.task = task
    def process(self):
        item = self.task.subject
        item.image_comic = item.generate_comic(user=self.task.owner)
        item.save()

class TaskGenerateSceneVideo:
    def __init__(self, task):
        self.task = task
    def process(self):
        item = self.task.subject
        clips = []
        first = None
        for video_item in item.video_items.all():
            clip = None
            if video_item.video:
                clip = VideoFileClip(video_item.video.path, audio=True)
            elif video_item.image:
                clip = ImageClip(video_item.image.path, duration=video_item.duration)
            if first:
                clip = clip.with_effects([Resize(width=first.w)])
            if not first:
                first = clip
            clips.append(clip)

        if clips:
            final_clip = concatenate_videoclips(clips, method="compose")
            name = f"video_{slugify(item.__class__.__name__)}_{slugify(item.name)}_{random.randint(1000,9999)}.mp4"
            filepath_relative = f"exported_videos/{name}"
            filepath_abs = os.path.join( settings.MEDIA_ROOT, filepath_relative)

            final_clip.write_videofile(filepath_abs, fps=24, codec='libx264',
                     audio_codec='aac', temp_audiofile='temp-audio.m4a', remove_temp=True)
            out = FilerImage.objects.create(
                original_filename=name,
                file=filepath_relative,
                name=name
            )
            item.video = out
            item.save()