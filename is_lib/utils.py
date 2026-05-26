import math


class ColorTools:
    """
    0 draws least attention
    10 draws most attention
    """
    # darkest
    COLOR_0 = '#1D1D1DFF'
    COLOR_1 = '#101010FF'
    COLOR_2 = '#111111FF'
    # background
    COLOR_3 = '#1D1D1DFF'
    # darker halftone (intonation path)
    COLOR_4 = '#6F6F6FFF'
    # brighter halftone cirles
    COLOR_6 = '#6F6F6FFF'
    # bright light T
    COLOR_8 = '#F3F3F3FF'
    # brightest
    COLOR_10 = '#FFFFFFFF'

    TRANSPARENT_2 = '#00000022'

    @staticmethod
    def to_rgba_source(rgba):
        """
        Unpacked tuple from hex colors
        """
        color_string = rgba.lstrip('#')
        color = tuple(
            float(int(color_string[i:i+2], 16)) / 255.0
            for i in (0, 2, 4, 6)
            )
        return color


class NoteTools:
    A4 = 440
    C0 = A4*pow(2, -4.75)
    notes = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

    @classmethod
    def note_to_midi(cls, note):
        # Accepted notation is Note-Octave
        note, octave = note[:-1].upper(), int(note[-1])
        st = cls.notes.index(note)
        return 12 + octave * 12 + st

    @classmethod
    def midi_to_note(cls, midi):
        # Accepted notation is Note-Octave
        midi_rounded = int(midi)
        octave = midi_rounded // 12 - 1
        st_index = midi_rounded % 12
        return cls.notes[st_index] + str(octave)

    @classmethod
    def note_to_freq(cls, note):
        # Accepted notation is Note-Octave
        note, octave = note[:-1].upper(), int(note[-1])
        dn = cls.notes.index(note)
        return cls.C0 * pow(2, (octave*12 + dn) / 12)

    @classmethod
    def freq_to_note(cls, freq):
        h = round(12 * math.log2(freq/cls.C0))
        octave = h // 12
        n = h % 12
        return cls.notes[n] + str(octave)

    @classmethod
    def note_range(cls, note_min, note_max):
        note_min, oct_min = note_min[:-1].upper(), int(note_min[-1])
        note_max, oct_max = note_max[:-1].upper(), int(note_max[-1])
        index_min, index_max = \
            cls.notes.index(note_min), cls.notes.index(note_max)
        index, octave = index_min, oct_min
        note_range = []
        while True:
            note_range.append(f"{cls.notes[index]}{octave}")
            if index == index_max and octave == oct_max:
                break
            else:
                if index == len(cls.notes) - 1:
                    index, octave = 0, octave + 1
                else:
                    index = index + 1
        return note_range
