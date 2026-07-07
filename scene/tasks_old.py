from task.models import Task
from agent.models import GetContentsMixin
from moviepy import ImageClip, VideoFileClip, AudioFileClip, concatenate_videoclips
from moviepy.video.fx import Resize
import random
from django.utils.text import slugify
import os 
from django.conf import settings
import io
import zipfile
import tempfile
from django.core.files.base import ContentFile
from .resources import (
    StoryResource, CharacterResource, BackgroundResource, 
    PropResource, SceneResource, ActionResource
)

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

class TaskExtractScene:
    def __init__(self, task):
        self.task = task
    def process(self):
        item = self.task.subject
        log = item.generate_scene(user=self.task.owner)
        self.task.log(log)

class TaskGenerateText:
    def __init__(self, task):
        self.task = task
    def process(self):
        item = self.task.subject
        agent = self.task.thr
        if hasattr(item, 'generate_text'):
            item.generate_text(agent=agent, user=self.task.owner)
        elif self.task.payload and 'target_field' in self.task.payload:
            out = agent.generate(self, preset=GetContentsMixin.PRESET_TEXT, user=self.task.owner, target_field=self.task.payload['target_field'])
            setattr(self, self.task.payload['target_field'], out)
            self.save()
        else:
            raise ValueError("TaskGenerateText requires 'target_field' in task payload or custom generate text method on the model.")


class TaskGenerateScene:
    """
    Extract scene from text and generate a scene object with associated media.
    """
    def __init__(self, task):
        self.task = task
    def process(self):
        item = self.task.subject
        item.generate_scene(user=self.task.owner)
        item.save()

class TaskGenerateElements:
    """
    Iterates through all actions of a scene and triggers image generation 
    for any missing background (location), character (cast/actor), or prop,
    as well as voice generation for missing character voice samples.
    """
    def __init__(self, task):
        self.task = task

    def process(self):
        scene = self.task.subject
        elements = set()
        voices = set()

        for action in scene.actions.all():
            if action.background: elements.add(action.background)
            if action.actor: 
                elements.add(action.actor)
                if action.actor.voice: voices.add(action.actor.voice)
            for char in action.cast.all(): 
                elements.add(char)
                if char.voice: voices.add(char.voice)
            for prop in action.props.all(): elements.add(prop)
            if action.voice: voices.add(action.voice)

        for element in elements:
            if not element.image:
                self.task.log(f"Queueing image generation for {element.name} ({element.__class__.__name__})")
                Task.createTaskIfQueueEnabled(
                    subject=element,
                    task_type=settings.TASK_TYPE_GENERATE_IMAGE,
                    thr=scene,
                    owner=self.task.owner
                )

        for voice in voices:
            if not voice.audio_voice:
                self.task.log(f"Queueing voice generation for {voice.name}")
                Task.createTaskIfQueueEnabled(
                    subject=voice,
                    task_type=settings.TASK_TYPE_GENERATE_VOICE,
                    thr=scene,
                    owner=self.task.owner
                )

class TaskGenerateShots:
    """
    Generates images for all actions in a scene using the Google GenAI Batch API.
    Packs all missing background, character, prop, and action panel image generation requests
    into a single batch job, uploads it, polls for completion, and downloads/saves the results.
    """
    def __init__(self, task):
        self.task = task

    def process(self):
        from google import genai
        from google.genai import types
        from agent.models import Agent
        from filer.models.imagemodels import Image as FilerImage
        from PIL import Image
        import json
        import base64
        import time
        import tempfile
        import os
        from io import BytesIO

        scene = self.task.subject
        owner = self.task.owner
        
        objects_to_generate = {}  # key: (model_name, id) -> obj

        for action in scene.actions.all().order_by('order'):
            # Elements required for this action
            elements = []
            if action.background: elements.append(action.background)
            if action.actor: elements.append(action.actor)
            elements.extend(list(action.cast.all()))
            elements.extend(list(action.props.all()))

            # Ensure action-specific voice is generated if dialogue text exists (non-image task)
            if action.voice and action.text and not action.audio_voice:
                self.task.log(f"Queuing dialogue voice generation for action: {action.get_name()}")
                Task.createTaskIfQueueEnabled(
                    subject=action,
                    task_type=settings.TASK_TYPE_GENERATE_VOICE,
                    thr=scene,
                    owner=owner
                )

            # Identify missing element images
            for element in elements:
                if not element.image:
                    key = (element._meta.model_name, element.id)
                    if key not in objects_to_generate:
                        objects_to_generate[key] = element

            # Identify missing action images
            if not action.image:
                key = (action._meta.model_name, action.id)
                if key not in objects_to_generate:
                    objects_to_generate[key] = action

        if not objects_to_generate:
            self.task.log("No images are missing for this scene. Nothing to batch generate.")
            return

        # Fetch image agent and setup genai client
        image_agent = Agent.objects.filter(output_type=Agent.OUTPUT_TYPE_IMAGE).first()
        if not image_agent:
            raise ValueError("No agent configured for image output type.")

        client = image_agent.get_genai_client(owner)
        model_name = image_agent.agent_model.name

        self.task.log(f"Preparing batch request for {len(objects_to_generate)} images using model {model_name}...")

        requests_list = []
        for key, obj in objects_to_generate.items():
            preset = obj.PRESET_IMAGE
            contents = obj.get_contents(generate_self=True, preset=preset)
            instructions = image_agent.get_instructions(user=owner, preset=preset, obj=obj)
            contents.extend(instructions)

            parts = []
            for item in contents:
                if isinstance(item, str):
                    parts.append({"text": item})
                elif hasattr(item, "save") or isinstance(item, Image.Image):
                    buffered = BytesIO()
                    item.save(buffered, format="PNG")
                    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
                    parts.append({
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": img_str
                        }
                    })
                elif isinstance(item, dict) and "inline_data" in item:
                    parts.append(item)
                elif isinstance(item, dict) and "text" in item:
                    parts.append(item)
                else:
                    parts.append({"text": str(item)})

            request_data = {
                "key": f"{key[0]}:{key[1]}",
                "request": {
                    "contents": [
                        {"parts": parts}
                    ],
                    "generationConfig": {
                        "imageConfig": {
                            "aspectRatio": "9:16"
                        }
                    }
                }
            }
            requests_list.append(request_data)

        # Write requests to a temporary JSONL file
        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w+", delete=False, encoding="utf-8") as temp_file:
            for req in requests_list:
                temp_file.write(json.dumps(req) + "\n")
            temp_file_path = temp_file.name

        try:
            self.task.log(f"Uploading batch request file ({os.path.getsize(temp_file_path)} bytes) to Gemini Files API...")
            uploaded_file = client.files.upload(
                file=temp_file_path,
                config={'mime_type': 'text/plain'}
            )
            self.task.log(f"Uploaded file reference name: {uploaded_file.name}")
        finally:
            try:
                os.unlink(temp_file_path)
            except Exception:
                pass

        # Create the Batch Job
        self.task.log("Submitting batch job...")
        batch_job = client.batches.create(
            model=model_name,
            src=uploaded_file.name,
            config={'display_name': f"batch_images_scene_{scene.id}_{int(time.time())}"}
        )
        self.task.log(f"Submitted batch job: {batch_job.name}. Initial state: {batch_job.state}")

        # Poll status
        completed_states = {'JOB_STATE_SUCCEEDED', 'JOB_STATE_FAILED', 'JOB_STATE_CANCELLED'}
        
        def get_state_str(s):
            if hasattr(s, "name"):
                return s.name
            return str(s).split('.')[-1]

        state_str = get_state_str(batch_job.state)
        while state_str not in completed_states:
            self.task.log(f"Batch job {batch_job.name} state: {state_str}. Waiting 30 seconds...")
            time.sleep(30)
            batch_job = client.batches.get(name=batch_job.name)
            state_str = get_state_str(batch_job.state)

        # Clean up uploaded input file
        try:
            client.files.delete(name=uploaded_file.name)
            self.task.log("Cleaned up uploaded input file from Gemini.")
        except Exception as e:
            self.task.log(f"Failed to clean up input file '{uploaded_file.name}': {e}")

        if state_str != 'JOB_STATE_SUCCEEDED':
            error_msg = getattr(batch_job, 'error', 'Unknown error')
            raise ValueError(f"Batch job failed. Final state: {state_str}. Error details: {error_msg}")

        # Download results
        dest = batch_job.dest
        if hasattr(dest, "file_name"):
            result_file_name = dest.file_name
        elif isinstance(dest, dict):
            result_file_name = dest.get("file_name")
        else:
            result_file_name = getattr(dest, "file_name", None)

        if not result_file_name:
            raise ValueError(f"Could not retrieve output file name from batch job destination config: {dest}")

        self.task.log(f"Downloading results from output file '{result_file_name}'...")
        file_content_bytes = client.files.download(file=result_file_name)
        file_content = file_content_bytes.decode('utf-8')

        # Clean up the output file from Gemini storage
        try:
            client.files.delete(name=result_file_name)
            self.task.log("Cleaned up result file from Gemini storage.")
        except Exception as e:
            self.task.log(f"Failed to clean up result file '{result_file_name}': {e}")

        # Process results
        success_count = 0
        for line in file_content.splitlines():
            if not line.strip():
                continue
            try:
                result_data = json.loads(line)
            except Exception as e:
                self.task.log(f"Failed to parse result JSON line: {e}")
                continue

            key_str = result_data.get("key")
            response_dict = result_data.get("response")

            if not key_str or not response_dict:
                self.task.log(f"Skipping line missing 'key' or 'response': {line[:200]}")
                continue

            try:
                model_name_part, obj_id_str = key_str.split(":", 1)
                obj_id = int(obj_id_str)
            except Exception as e:
                self.task.log(f"Error parsing key '{key_str}': {e}")
                continue

            obj = objects_to_generate.get((model_name_part, obj_id))
            if not obj:
                self.task.log(f"Received results for unexpected key '{key_str}'")
                continue

            try:
                # Reconstruct GenerateContentResponse from Pydantic schema
                response = types.GenerateContentResponse.model_validate(response_dict)
                img_filer = image_agent.save_image(response, obj)
                if img_filer:
                    obj.image = img_filer
                    obj.save()
                    self.task.log(f"Saved image for {model_name_part} #{obj_id} ({obj})")
                    success_count += 1
                else:
                    self.task.log(f"Failed to save image for {model_name_part} #{obj_id}: save_image returned None")
            except Exception as e:
                self.task.log(f"Error processing image response for {model_name_part} #{obj_id}: {e}")

        self.task.log(f"Batch generation completed. Successfully updated {success_count} / {len(objects_to_generate)} images.")

class TaskSyncExport:
    def __init__(self, task):
        self.task = task

    def process(self):
        from .models import Action
        sync_item = self.task.subject
        sync = sync_item.sync
        story = sync.story
        from filer.models.filemodels import File as FilerFile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # 1. Export Data as CSVs
            zip_file.writestr('data/story.csv', StoryResource().export(story.__class__.objects.filter(id=story.id)).csv)
            zip_file.writestr('data/characters.csv', CharacterResource().export(story.characters.all()).csv)
            zip_file.writestr('data/backgrounds.csv', BackgroundResource().export(story.backgrounds.all()).csv)
            zip_file.writestr('data/props.csv', PropResource().export(story.props.all()).csv)
            
            scenes = story.scenes.all()
            zip_file.writestr('data/scenes.csv', SceneResource().export(scenes).csv)
            
            actions = Action.objects.filter(scene__in=scenes)
            zip_file.writestr('data/actions.csv', ActionResource().export(actions).csv)

            # 2. Helper to add media files
            def add_filer_file(filer_file, folder):
                if filer_file and hasattr(filer_file, 'file') and filer_file.file:
                    try:
                        file_path = filer_file.file.path
                        arcname = os.path.join(folder, os.path.basename(file_path))
                        if arcname not in zip_file.namelist():
                            zip_file.write(file_path, arcname)
                    except Exception:
                        pass

            for char in story.characters.all():
                add_filer_file(char.image, "media/characters")
            for bg in story.backgrounds.all():
                add_filer_file(bg.image, "media/backgrounds")
                add_filer_file(bg.image_refine, "media/backgrounds")
            for prop in story.props.all():
                add_filer_file(prop.image, "media/props")
            for action in actions:
                add_filer_file(action.image, "media/actions")
                add_filer_file(action.image_comic, "media/actions")
                add_filer_file(action.video, "media/videos")
                add_filer_file(action.audio_voice, "media/audio")

        buffer.seek(0)
        filename = f"export_{slugify(story.name)}_{sync_item.id}.zip"
        
        out_file = FilerFile.objects.create(
            original_filename=filename,
            file=ContentFile(buffer.read(), name=filename),
            name=filename
        )
        sync_item.zip_file = out_file
        sync_item.save()
        
        sync.last_file_out = out_file
        sync.save()

class TaskSyncImport:
    def __init__(self, task):
        self.task = task

    def process(self):
        sync_item = self.task.subject
        sync = sync_item.sync
        story = sync.story
        
        if not sync_item.zip_file:
            self.task.log("Missing zip file for import")
            return

        # Update sync model to track the last imported file
        sync.last_file_in = sync_item.zip_file
        sync.save()
        
        # Unzip to temp folder - placeholder for robust resource import logic
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                with zipfile.ZipFile(sync_item.zip_file.file.path, 'r') as zf:
                    zf.extractall(temp_dir)
                self.task.log(f"Import extracted to {temp_dir}. Deep resource sync from zip requires resource adjustment.")
            except Exception as e:
                self.task.log(f"Extraction failed: {str(e)}")
