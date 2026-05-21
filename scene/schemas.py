from pydantic import BaseModel
from .models import Scene, Action, Character, Prop, Background
from typing import List, Optional

class CharacterSchema(BaseModel):
    name: str
    prompt: str

class PropSchema(BaseModel):
    name: str
    prompt: str

class BackgroundSchema(BaseModel):
    name: str
    prompt: str

class ActionSchema(BaseModel):
    name: str
    prompt: str
    cast: List[str] = []
    props: List[str] = []


class SceneSchema(BaseModel):
    name: str
    location: BackgroundSchema
    characters: List[CharacterSchema]
    props: List[PropSchema]
    actions: List[ActionSchema]

    def sync_model(self, source):
        """
        Syncs the structured Pydantic data with Django models.
        Assumes source provides get_story() and get_scene().
        """
        story = source.get_story()
        
        # Sync the Scene itself to avoid duplicates if the same name is used
        scene, _ = Scene.objects.update_or_create(
            name=self.name,
            story=story
        )
        
        # Link the source turn to this scene if not already linked
        if hasattr(source, 'scene') and source.scene is None:
            source.scene = scene
            source.save()

        # 1. Sync Location (Background)
        background, _ = Background.objects.update_or_create(
            name=self.location.name,
            story=story,
            defaults={'prompt': self.location.prompt}
        )

        # 2. Sync Global Characters for the Story
        char_map = {}
        if self.characters:
            for char_data in self.characters:
                char, _ = Character.objects.update_or_create(
                    name=char_data.name,
                    story=story,
                    defaults={'prompt': char_data.prompt}
                )
                char_map[char.name] = char

        # 3. Sync Global Props for the Story
        prop_map = {}
        if self.props:
            for prop_data in self.props:
                prop_obj, _ = Prop.objects.update_or_create(
                    name=prop_data.name,
                    story=story,
                    defaults={'prompt': prop_data.prompt}
                )
                prop_map[prop_obj.name] = prop_obj

        # 4. Sync Actions for the Scene
        if self.actions:
            for i, action_data in enumerate(self.actions):
                action = Action.objects.create(
                    scene=scene,
                    name=action_data.name,
                    order=i,
                    prompt=action_data.prompt,
                    background=background
                )
                if action_data.cast:
                    action.cast.set([char_map[name] for name in action_data.cast if name in char_map])
                if action_data.props:
                    action.props.set([prop_map[name] for name in action_data.props if name in prop_map])
        return scene


class MultiSceneSchema(BaseModel):
    scenes: List[SceneSchema]

    def sync_model(self, source):
        last_scene = None
        for scene_data in self.scenes:
            last_scene = scene_data.sync_model(source)
        return last_scene
    