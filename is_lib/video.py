import os
import ffmpeg
from is_lib.audio import move_to_wav
from is_lib.image import ImageMaker


class VideoMaker:
    """
    Creates the intonation video 
    """
    TARGET_DIR = 'clips'

    def __init__(
        self,
        maker_id,
        media_dir,
        temp_dir
    ):
        self.clip_dir = os.path.join(media_dir, self.TARGET_DIR)
        self.wav_dir = os.path.join(temp_dir, 'wavs')
        # image maker created the frames
        self.maker = ImageMaker(temp_dir, maker_id)

    def make_video(
        self,
        mp3_path,
        data
    ):
        self.maker.make_images(data)
        pattern = self.maker.save_images()
        wav_path = move_to_wav(mp3_path, self.wav_dir)
        filename = os.path.basename(wav_path)
        filename = f"{filename[:-4]}.mp4"
        path_output = os.path.join(self.clip_dir, filename)
        if not os.path.exists(path_output):
            outdict = {
                'vcodec': 'h264',
                'shortest': None
            }
            image = ffmpeg.input(pattern)
            audio = ffmpeg.input(wav_path)
            ffmpeg.output(image, audio, path_output, **outdict).run()
        return f"{self.TARGET_DIR}/{filename}"


class TutorialVideoMaker:
    """
    A video tutorial is the concatenation of the audio videos
    """
    TARGET_DIR = 'tutorials'

    def __init__(
        self,
        media_dir,
    ):
        self.tutorial_dir = os.path.join(media_dir, self.TARGET_DIR)

    def make(self, clips, filename):
        path_output = os.path.join(
            self.tutorial_dir,
            filename
        )
        inputs = []
        for clip in clips:
            i = ffmpeg.input(clip)
            inputs.append(i['v'])
            inputs.append(i['a'])
        joined = ffmpeg.concat(
            *inputs,
            v=1,
            a=1,
            unsafe=True
        )
        joined.output(path_output).run()
        return f"{self.TARGET_DIR}/{filename}"
