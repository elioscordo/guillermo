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



class TaskGenerateSceneActions:
    """
    Generates images for all actions in a scene using the Google GenAI Batch API.
    Packs all missing background, character, prop, and action panel image generation requests
    into a single batch job, uploads it, polls for completion, and downloads/saves the results.
    """
    def __init__(self, task):
        self.task = task

    def process(self):

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
