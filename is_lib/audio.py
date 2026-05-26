import os
from aubio import source, pitch
import ffmpeg
import numpy as np


def mp3_to_wav(mp3_path, wav_path):
    try:
        mp3 = ffmpeg.input(mp3_path)
        ffmpeg.output(mp3, wav_path).run(
            capture_stdout=True,
            capture_stderr=True
        )
    except ffmpeg.Error as e:
        print('stdout:', e.stdout.decode('utf8'))
        print('stderr:', e.stderr.decode('utf8'))
        raise e


def move_to_wav(mp3_path, wav_dir):
    basename = os.path.basename(mp3_path)
    wavpath = os.path.join(wav_dir, f"{basename[:-4]}.wav")
    if not os.path.exists(wavpath):
        mp3_to_wav(mp3_path, wavpath)
    return wavpath


class AudioAnalyst:
    debug = True
    hop = 512  # downsample # hop size
    downsample = 1
    win_s = 4096  # downsample # fft size
    tolerance = 0.8
    silence = -40
    clean = False
    clean_tollerance = 0.35
    clean_value = -1.0
    analysis = None

    def __init__(
        self,
        temp_dir,
        unit='midi',
        method='yin',
        samplerate=12800,
        hop=512,
        win_s=4096
    ):
        """
        Default values  128000 / 512 = 25 sample per second.
        """
        self.wav_dir = os.path.join(temp_dir, 'wavs')
        if not os.path.exists(self.wav_dir):
            os.makedirs(self.wav_dir)
        self.unit = unit
        self.hop = hop
        self.win_s = win_s
        # Support to frequency not completed and never used
        self.is_midi = self.unit == 'midi'
        self.method = method
        self.samplerate = samplerate
        self.pitch_o = pitch(
            self.method, self.win_s, self.hop, self.samplerate
        )
        self.pitch_o.set_unit(self.unit)
        self.pitch_o.set_silence(self.silence)
        self.pitch_o.set_tolerance(self.tolerance)

    def analyse(
        self,
        filepath
    ):
        if (filepath.split('.')[-1].lower() == 'mp3'):
            basename = os.path.basename(filepath)
            wavpath = os.path.join(self.wav_dir, f"{basename[:-4]}.wav")
            if not os.path.exists(wavpath):
                mp3_to_wav(filepath, wavpath)
        s = source(wavpath, self.samplerate, self.hop)
        total_frames = 0
        pitches = []
        confidences = []
        while True:
            samples, read = s()
            pitch = self.pitch_o(samples)[0]
            confidence = self.pitch_o.get_confidence()
            if self.clean and confidence < self.clean_tollerance:
                pitch = self.clean_value
            pitches += [pitch]
            confidences += [confidence]
            total_frames += read
            if read < self.hop:
                break
        # clean results
        pitches = np.array(pitches)
        pitches = np.ma.masked_where(
            pitches <= 12.0,
            pitches
        )
        # save and return analysis
        return self.set_analysis(
            filepath,
            pitches
        )

    def set_analysis(
        self,
        filepath,
        samples
    ):
        """
        Set samples and compute stats
        """
        self.samples = samples
        self.max_x = self.samples.size
        self.min_y = np.min(self.samples)
        self.max_y = np.max(self.samples)
        self.analysis = {
            'samples': self.samples.tolist(),
            'tolerance': str(self.tolerance),
            'silence': str(self.silence),
            'hop': str(self.hop),
            'samplerate': str(self.samplerate),
            'max_x': str(self.max_x),
            'min_y': str(self.min_y),
            'max_y': str(self.max_y),
            'unit': str(self.unit),
            'duration': ffmpeg.probe(filepath)['format']['duration']
        }
        return self.analysis

