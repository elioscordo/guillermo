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
    background: str

class SceneSchema(BaseModel):
    name: str
    locations: List[BackgroundSchema]
    characters: List[CharacterSchema]
    props: List[PropSchema]
    actions: List[ActionSchema]

    def sync_model(self, scene):
        """
        Syncs the structured Pydantic data with Django models.
        Assumes source provides get_story() and get_scene().
        """
        story = scene.story
        
        scene.name = self.name
        scene.save()
        # 2. Sync Global Characters for the Story
        location_map = {}
        if self.characters:
            for back_data in self.locations:
                item = Background.objects.update_or_create(
                    name=back_data.name,
                    story=story,
                    defaults={'prompt': back_data.prompt}
                )   
                location_map[item[0].name] = item
                    
        char_map = {}
        if self.characters:
            for char_data in self.characters:
                item = Character.objects.update_or_create(
                    name=char_data.name,
                    story=story,
                    defaults={'prompt': char_data.prompt}
                )
                char_map[item[0].name] = item

        # 3. Sync Global Props for the Story
        prop_map = {}
        if self.props:
            for prop_data in self.props:
                item = Prop.objects.update_or_create(
                    name=prop_data.name,
                    story=story,
                    defaults={'prompt': prop_data.prompt}
                )
                prop_map[item[0].name] = item

        # 4. Sync Actions for the Scene
        action_map = {}
        if self.actions:
            for i, action_data in enumerate(self.actions):
                action = Action.objects.create(
                    scene=scene,
                    name=action_data.name,
                    order=i,
                    prompt=action_data.prompt,
                    background=location_map.get(action_data.background)[0]
                )
                if action_data.cast:
                    action.cast.set([char_map[name][0] for name in action_data.cast if name in char_map])
                if action_data.props:
                    action.props.set([prop_map[name][0] for name in action_data.props if name in prop_map])
                action_map[action.name] = action
        return {
            'locations': [(item[0].name, item[1]) for item in location_map.values()],
            'characters': [(item[0].name, item[1]) for item in char_map.values()],
            'props': [(item[0].name, item[1]) for item in prop_map.values()],
            'actions': [item.name for item in action_map.values()]
        }


class MultiSceneSchema(BaseModel):
    scenes: List[SceneSchema]

    def sync_model(self, source):
        last_scene = None
        for scene_data in self.scenes:
            last_scene = scene_data.sync_model(source)
        return last_scene
    