import base64
from django.conf import settings


def get_genai_client(user=None):
    from google import genai
    if user and hasattr(user, 'agent_profile') and user.agent_profile.google_api_key:
        api_key = user.agent_profile.google_api_key.api_key
        genai_client = genai.Client(
            vertexai=True,
            api_key=api_key
        )
    else:
        raise Exception("User does not have an API key configured. Please set up your API key in your profile settings.")
    return genai_client


# Set up the wave file to save the output:
def wave_file(filename, pcm, channels=1, rate=24000, sample_width=2):
    import wave
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)