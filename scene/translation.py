from modeltranslation.translator import register, TranslationOptions
from .models import Action, ComicAction, VideoAction, VoiceAction, ActionOrganizer

@register(Action)
class ActionTranslationOptions(TranslationOptions):
    fields = ('prompt_comic', 'prompt_voice', 'image_comic', 'audio_voice')

@register(ComicAction)
class ComicActionTranslationOptions(TranslationOptions):
    pass

@register(VoiceAction)
class VoiceActionTranslationOptions(TranslationOptions):
    pass

@register(VideoAction)
class VideoActionTranslationOptions(TranslationOptions):
    pass

@register(ActionOrganizer)
class ActionOrganizerTranslationOptions(TranslationOptions):
    pass

