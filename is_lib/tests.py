
import os

from django.test import TestCase
from django.conf import settings
from filer.models import File
from is_lib.audio import AudioAnalyst
from is_lib.dsp import resize
from is_lib.image import ImageMaker
from is_lib.manim import ISPlot
from audiomixer.models import Audio, AudioAnalysis, Language, Task
from audiomixer.tasks import TaskVideo


class TestImageMaker(TestCase):

    def setUp(self):
        self.audio_path = os.path.join(settings.MEDIA_ROOT, 'mp3/test1.mp3')
        analyst = AudioAnalyst(settings.TEMP_DIR)
        # set data
        self.data = analyst.analyse(self.audio_path)
        self.data['text'] = 'text'

    def test_image_maker(self):
        maker = ImageMaker(settings.TEMP_DIR, '0000_test_1')
        maker.make_images(self.data)
        pattern = maker.save_images()

        self.assertTrue(
             pattern
        )


class TestManimSine(TestCase):

    def setUp(self):
        self.audio_path = os.path.join(settings.MEDIA_ROOT, 'mp3/test-sine.mp3')
        analyst = AudioAnalyst(settings.TEMP_DIR, hop=1024)
        self.data = analyst.analyse(self.audio_path)
        self.data['text'] = 'text'
        self.data['credits'] = 'credits'

    def test_manim_animation(self):

        analysis = AudioAnalysis.objects.create(
          data=self.data
        )
        language = Language.objects.create(
          code="it",
          name="Italian",
        )
        audio = Audio.objects.create()
        audio.analysis = analysis
        audio.language = language
        audio.file = File(
                file=self.audio_path,
                name=os.path.basename(self.audio_path),
                original_filename=os.path.basename(self.audio_path)
        )
        scene = ISPlot()
        scene.audios = [audio]
        scene.render()
        path = scene.renderer.file_writer.movie_file_path
        print(f"video generated with success {path}")


class TestManimSpeech(TestCase):

    def test_manim_animation(self):
        self.audio_path = os.path.join(settings.MEDIA_ROOT, "1_it-it_it-IT-Neural2-A_0_5.mp3")
        analyst = AudioAnalyst(settings.TEMP_DIR, hop=2048)
        self.data = analyst.analyse(self.audio_path)
        self.data['text'] = 'text'
        self.data['credits'] = 'credits'
        analysis = AudioAnalysis.objects.create(
          data=self.data
        )
        language = Language.objects.create(
          code="it",
          name="Italian",
        )
        audio = Audio.objects.create()
        audio.analysis = analysis
        audio.language = language
        audio.file = File(
                file=self.audio_path,
                name=os.path.basename(self.audio_path),
                original_filename=os.path.basename(self.audio_path)
        )
        scene = ISPlot()
        scene.audios = [audio]
        scene.render()
        path = scene.renderer.file_writer.movie_file_path
        print(f"video generated with success {path}")


class TestDSP(TestCase):

    def test_ts(self):
        input = os.path.join(settings.MEDIA_ROOT, 'mp3/test-speech.mp3')
        output = os.path.join(settings.MEDIA_ROOT, 'mp3/test-it-portata.mp3')
        resize(input, output, ratio=3)


class TestVideoMaker(TestCase):
    def setUp(self):
        self.audio_path = os.path.join(settings.MEDIA_ROOT, 'mp3/test-it-portata.mp3')
        # /Users/elio/projects/is/media_server/clips/test-it-portata.mp4
        analyst = AudioAnalyst(settings.TEMP_DIR, hop=1024)
        self.data = analyst.analyse(self.audio_path)
        self.data['text'] = 'text'
        self.data['credits'] = 'credits'

    def test_video(self):

        analysis = AudioAnalysis.objects.create(
          data=self.data
        )
        language = Language.objects.create(
          code="it",
          name="Italian",
        )
        audio = Audio.objects.create()
        audio.analysis = analysis
        audio.language = language
        audio.file = File(
                file=self.audio_path,
                name=os.path.basename(self.audio_path),
                original_filename=os.path.basename(self.audio_path)
        )
        task = Task.objects.create(subject=audio)

        task_video = TaskVideo(task)
        task_video.process()
        print(audio.analysis.video)
        self.assertTrue(audio.analysis.video is not None)