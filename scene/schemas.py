from pydantic import BaseModel
from typing import List, Optional

from agent.models import Prompt
from agent.schemas import SyncReport, get_asset_sync_info


def remove_null_values(data: dict) -> dict:
    """
    Recursively removes keys with None values from dictionaries.
    Prevents LLM-injected null values from overwriting existing model fields.
    """
    clean = {}
    for key, val in data.items():
        if val is None:
            continue
        if isinstance(val, dict):
            val = remove_null_values(val)
            if not val:
                continue
        clean[key] = val
    return clean


def update_or_create_clean(model_class, defaults=None, **lookup):
    """
    Safe update_or_create pattern that strips null values from defaults
    before editing existing instances, preventing data loss.
    """
    clean_defaults = remove_null_values(defaults or {})
    obj = model_class.objects.filter(**lookup).first()
    if obj:
        if clean_defaults:
            for key, val in clean_defaults.items():
                if isinstance(val, dict) and hasattr(obj, key):
                    existing_val = getattr(obj, key)
                    if isinstance(existing_val, dict):
                        val = {**existing_val, **val}
                setattr(obj, key, val)
            obj.save()
        return obj, False
    return model_class.objects.create(**lookup, **clean_defaults), True


class Parameters(BaseModel):
    buffer_in: Optional[float] = None
    buffer_out: Optional[float] = None
    duration: Optional[int] = None
    iterations: Optional[int] = None

class VoiceSchema(BaseModel):
    name: str
    prompt: Optional[str] = None
    google_voice: Optional[str] = None

class GoogleVoiceSchema(BaseModel):
    name: str
    description: str

class CharacterSchema(BaseModel):
    name: str
    prompt: Optional[str] = None

class PropSchema(BaseModel):
    name: str
    prompt: Optional[str] = None

class BackgroundSchema(BaseModel):
    name: str
    prompt: Optional[str] = None

class ActionSchema(BaseModel):
    name: str
    prompt: Optional[str] = None
    prompt_voice: Optional[str] = None
    prompt_comic: Optional[str] = None
    prompt_video: Optional[str] = None
    cast: Optional[List[str]] = None
    props: Optional[List[str]] = None
    background: Optional[str] = None
    voice: Optional[str] = None


class AssetsSchema(BaseModel):
    locations: Optional[List[BackgroundSchema]] = None
    characters: Optional[List[CharacterSchema]] = None
    props: Optional[List[PropSchema]] = None
    voices: Optional[List[VoiceSchema]] = None

    def sync_model(self, obj):
        from agent.models import GoogleVoice
        from .models import Character, Prop, Background, Voice, Scene, Story

        scene, story = None, None
        if isinstance(obj, Story):
            story = obj
        elif isinstance(obj, Scene):
            scene = obj
            story = scene.story
        voice_map = {}
        if self.voices:
            for voice_data in self.voices:
                gv = GoogleVoice.objects.filter(name=voice_data.google_voice).first() if voice_data.google_voice else None
                item = update_or_create_clean(
                    Voice,
                    name=voice_data.name,
                    story=story,
                    defaults={
                        'prompt': voice_data.prompt,
                        'google_voice': gv
                    }
                )
                voice_map[item[0].name] = item

        location_map = {}
        if self.locations:
            for back_data in self.locations:
                item = update_or_create_clean(
                    Background,
                    name=back_data.name,
                    story=story,
                    defaults={'prompt': back_data.prompt}
                )   
                location_map[item[0].name] = item

        char_map = {}
        if self.characters:
            for char_data in self.characters:
                item = update_or_create_clean(
                    Character,
                    name=char_data.name,
                    story=story,
                    defaults={'prompt': char_data.prompt}
                )
                char_map[item[0].name] = item

        prop_map = {}
        if self.props:
            for prop_data in self.props:
                item = update_or_create_clean(
                    Prop,
                    name=prop_data.name,
                    story=story,
                    defaults={'prompt': prop_data.prompt}
                )
                prop_map[item[0].name] = item

        if scene is not None:
            if location_map:
                scene.locations.add(*[item[0] for item in location_map.values()])
            if char_map:
                scene.cast.add(*[item[0] for item in char_map.values()])
            if prop_map:
                scene.props.add(*[item[0] for item in prop_map.values()])
            if voice_map:
                scene.voices.add(*[item[0] for item in voice_map.values()])

        sync_info = {
            'locations': [get_asset_sync_info(item[0], item[1]) for item in location_map.values()],
            'characters': [get_asset_sync_info(item[0], item[1]) for item in char_map.values()],
            'props': [get_asset_sync_info(item[0], item[1]) for item in prop_map.values()],
            'voices': [get_asset_sync_info(item[0], item[1]) for item in voice_map.values()]
        }

        return sync_info, voice_map, location_map, char_map, prop_map


class SceneSchema(BaseModel):
    shots: Optional[List[ActionSchema]] = None
    locations: Optional[List[BackgroundSchema]] = None
    characters: Optional[List[CharacterSchema]] = None
    props: Optional[List[PropSchema]] = None
    voices: Optional[List[VoiceSchema]] = None

    def sync_model(self, scene):
        """
        Syncs the structured Pydantic data with Django models.
        Assumes source provides get_story() and get_scene().
        """
        story = scene.story
        was_created = scene._state.adding
        scene.save()

        # Sync assets using AssetsSchema
        assets = AssetsSchema(
            locations=self.locations or [],
            characters=self.characters or [],
            props=self.props or [],
            voices=self.voices or []
        )
        sync_info, voice_map, location_map, char_map, prop_map = assets.sync_model(scene)

        # 5. Sync Shots for the Scene
        shot_reports = []
        if self.shots:
            from .models import Action, Voice, Background, Character, Prop
            for i, shot_data in enumerate(self.shots):
                voice_obj = None
                if shot_data.voice:
                    if shot_data.voice in voice_map:
                        voice_obj = voice_map[shot_data.voice][0]
                    elif story:
                        voice_obj = Voice.objects.filter(story=story, name=shot_data.voice).first()

                bg_obj = None
                if shot_data.background:
                    if shot_data.background in location_map:
                        bg_obj = location_map[shot_data.background][0]
                    elif story:
                        bg_obj = Background.objects.filter(story=story, name=shot_data.background).first()

                shot, created = update_or_create_clean(
                    Action,
                    scene=scene,
                    name=shot_data.name,
                    defaults={
                        'order': i*2,
                        'prompt': shot_data.prompt,
                        'prompt_comic': shot_data.prompt_comic,
                        'prompt_video': shot_data.prompt_video,
                        'prompt_voice': shot_data.prompt_voice,
                        'voice': voice_obj,
                        'background': bg_obj,
                    }
                )
                if shot_data.cast is not None:
                    cast_objs = []
                    for name in shot_data.cast:
                        if name in char_map:
                            cast_objs.append(char_map[name][0])
                        elif story:
                            char_item = Character.objects.filter(story=story, name=name).first()
                            if char_item:
                                cast_objs.append(char_item)
                    if cast_objs:
                        shot.cast.set(cast_objs)

                if shot_data.props is not None:
                    prop_objs = []
                    for name in shot_data.props:
                        if name in prop_map:
                            prop_objs.append(prop_map[name][0])
                        elif story:
                            prop_item = Prop.objects.filter(story=story, name=name).first()
                            if prop_item:
                                prop_objs.append(prop_item)
                    if prop_objs:
                        shot.props.set(prop_objs)

                shot_reports.append(get_asset_sync_info(shot, created))

        scene_report = get_asset_sync_info(scene, was_created)

        return {
            **sync_info,
            'actions': shot_reports,
            'scene': scene_report
        }


class MultiSceneSchema(BaseModel):
    scenes: Optional[List[SceneSchema]] = None

    def sync_model(self, source):
        results = []
        if self.scenes:
            for scene_data in self.scenes:
                results.append(scene_data.sync_model(source))
        return results


from agent.models import OutputWithMessageSchema, CreateInstructionsSchema


class StoryScenesSchema(BaseModel):
    scenes: Optional[List[SceneSchema]] = None

    def sync_model(self, story):
        from .models import Scene
        synced_scenes = []
        if self.scenes:
            for scene_data in self.scenes:
                scene, created = update_or_create_clean(
                    Scene,
                    story=story,
                    name=scene_data.name,
                    defaults={
                        'prompt_plot': scene_data.prompt_plot,
                        'order': scene_data.order,
                    }
                )
                scene_data.sync_model(scene)
                synced_scenes.append(get_asset_sync_info(scene, created))
        return {
            'scenes': synced_scenes
        }


class ShotTranslationSchema(BaseModel):
    shot_id: Optional[int] = None
    shot_name: Optional[str] = None
    name: Optional[str] = None
    prompt_voice: Optional[str] = None
    prompt_voice_en: Optional[str] = None
    prompt_voice_it: Optional[str] = None
    prompt_voice_es: Optional[str] = None
    prompt_voice_pt: Optional[str] = None
    prompt_voice_fr: Optional[str] = None
    suggested_default_improvement: Optional[str] = None
    prompt_comic: Optional[str] = None
    prompt_comic_en: Optional[str] = None
    prompt_comic_it: Optional[str] = None
    prompt_comic_es: Optional[str] = None
    prompt_comic_pt: Optional[str] = None
    prompt_comic_fr: Optional[str] = None


class SceneTranslationSchema(BaseModel):
    shots: Optional[List[ShotTranslationSchema]] = []

    def find_action(self, scene, shot_data):
        from .models import Action
        actions = scene.actions if hasattr(scene, 'actions') else Action.objects.filter(scene__story=scene)
        if shot_data.shot_id:
            action = actions.filter(id=shot_data.shot_id).first()
            if action:
                return action
        name = shot_data.shot_name or shot_data.name
        if name:
            return actions.filter(name=name).first()
        return None

    def apply_shot_translation(self, action, shot_data, default_lang, configured_langs):
        for lang in configured_langs:
            voice_val = getattr(shot_data, f"prompt_voice_{lang}", None)
            if not voice_val and lang == default_lang:
                voice_val = shot_data.prompt_voice
            if voice_val:
                setattr(action, f"prompt_voice_{lang}", voice_val)
                if lang == default_lang:
                    action.prompt_voice = voice_val

            comic_val = getattr(shot_data, f"prompt_comic_{lang}", None)
            if not comic_val and lang == default_lang:
                comic_val = shot_data.prompt_comic
            if comic_val:
                setattr(action, f"prompt_comic_{lang}", comic_val)
                if lang == default_lang:
                    action.prompt_comic = comic_val

        if shot_data.suggested_default_improvement:
            setattr(action, f"prompt_voice_{default_lang}", shot_data.suggested_default_improvement)
            action.prompt_voice = shot_data.suggested_default_improvement

        action.save()
        return action

    def sync_model(self, scene):
        from django.conf import settings
        default_lang = getattr(settings, 'MODELTRANSLATION_DEFAULT_LANGUAGE', 'en')
        configured_langs = list(getattr(settings, 'MODELTRANSLATION_LANGUAGES', ('en', 'it', 'es', 'pt', 'fr')))

        shot_reports = []
        if self.shots:
            for shot_data in self.shots:
                action = self.find_action(scene, shot_data)
                if action:
                    self.apply_shot_translation(action, shot_data, default_lang, configured_langs)
                    shot_reports.append(get_asset_sync_info(action, False))

        return {
            'shots': shot_reports,
            'scene': get_asset_sync_info(scene, False)
        }


TranslationSchema = SceneTranslationSchema