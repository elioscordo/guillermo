import os
from google.cloud import texttospeech
from google.oauth2 import service_account

FILENAME_MAX_CHARS = 40


class GoogleSpeaker:
    FILENAME_EXTENSION = 'mp3'

    def __init__(self, credentials_json, folder):
        credentials = service_account.Credentials.from_service_account_file(
            credentials_json)
        self.client = texttospeech.TextToSpeechClient(
            credentials=credentials
        )
        self.folder = folder

    def filename_from_text(self, text_hash, language, voice_name, rate):
        out = f"{text_hash}_{language}_{voice_name}_{str(rate).replace('.','_')}.mp3"
        return out

    def is_voice_in_preset(self, preset, voice_name):
        include_filter = 'include' in preset and not any(
                    x.lower() in voice_name for x in preset['include'])
        exclude_filter = 'exclude' in preset and any(
                    x.lower() in voice_name for x in preset['exclude']
        )
        return not include_filter and not exclude_filter

    def repeat(
        self,
        text,
        text_hash,
        preset={'rates': "0.5,0.6"},
        lang='en'
    ):
        out = []
        max_count = None
        if 'max' in preset:
            max_count = preset['max']
        for rate in preset['rates'].split(','):
            count = 0
            for voice in self.client.list_voices(language_code=lang).voices:
                voice_name = voice.name.lower()
                if self.is_voice_in_preset(preset, voice_name):
                    name, path = self.speak(
                        text,
                        text_hash,
                        language=lang,
                        rate=float(rate),
                        voice_name=voice.name,
                    )
                    out.append(
                        {
                            'language': lang,
                            'rate': rate,
                            'voice': voice.name,
                            'path': path,
                            'name': name,
                            'languages': voice.language_codes
                        })
                    if max_count and count >= max_count-1:
                        break
                count += 1
        return out

    def get_path(self, filename):
        return os.path.join(self.folder, filename)

    def speak(
        self,
        text,
        text_hash,
        rate=0.8,
        language='en-US',
        filename=None,
        voice_name=None
    ):
        """
        Create the audio file from text.
        """
        filename = self.filename_from_text(
             text_hash,
             language,
             voice_name,
             rate
        )
        path = self.get_path(filename)
        if not os.path.exists(path):
            synthesis_input = texttospeech.SynthesisInput(text=text)
            voice = texttospeech.VoiceSelectionParams(
                language_code=language,
                name=voice_name
            )
            # Select the type of audio file you want returned
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=rate
            )
            # voice parameters and audio file type
            response = self.client.synthesize_speech(
                input=synthesis_input, voice=voice, audio_config=audio_config
            )
            # The response's audio_content is binary.
            with open(path, "wb") as out:
                out.write(response.audio_content)
        return filename, path
