import json
import math
import random
import os
import string
import cairo
import numpy as np
import shutil
from .utils import ColorTools, NoteTools


class ImageMaker:
    """
    Make the images for the video and save them in the target folder
    """
    WIDTH, HEIGHT = 1280, 720
    PADDING = 20
    BENCHMARKS = 4
    DRAW_GRID = False
    DRAW_HISTOGRAM_PEEKS = False
    PATTERN = 'frame_%d.png'

    def __init__(self, dir, maker_id):
        self.folder = os.path.join(dir, 'images', maker_id)
        if (os.path.exists(self.folder)):
            shutil.rmtree(self.folder)
        os.makedirs(self.folder)

    def __getattr__(self, name):
        """ Shortcut.
            The data dictionary is accesible through the object
        """
        if name in self.data:
            return self.data[name]

    def make_images(self, data):
        """
        Create video frames
        """
        self.data = data
        self.samples = np.array(self.data['samples'])
        self.set_strip_samples()
        self.images = []
        for x, y in enumerate(self.samples):
            surface_join = cairo.ImageSurface(
                cairo.FORMAT_ARGB32, self.WIDTH, self.HEIGHT
            )
            ctx = cairo.Context(surface_join)
            ctx.rectangle(0, 0, self.WIDTH, self.HEIGHT)
            ctx.set_source_rgba(*ColorTools.to_rgba_source(ColorTools.COLOR_0))
            ctx.fill()
            # Add the background
            self.cairo_draw_background(ctx)
            # Add the foreground
            if y:
                x1 = self.PADDING + \
                    self.to_image_dim(
                        x - self.first_index, 'path_x'
                    ) + self.rects()['path'][0]
                y1 = self.PADDING + \
                    self.to_image_dim(y, 'path_y') + self.rects()['path'][1]
                ctx.arc(x1, y1, 15, 0, 2 * math.pi)
                ctx.set_source_rgba(
                    *ColorTools.to_rgba_source(ColorTools.COLOR_10)
                )
                ctx.fill()
            self.images.append(surface_join)
        return self.images

    def save_images(self):
        """
        Save the images and return the pattern to retrieve them
        """

        for x, image in enumerate(self.images):
            imagepath = self.target_path(self.PATTERN % x)
            image.write_to_png(imagepath)
        return self.target_path(self.PATTERN)

    def rects(self):
        """
        Measurements of elements within the image
        """
        return {
            'text': (60, 60, 1120, 140),
            'path': (60, 160, 1160, 480),
        }

    def target_path(self, filename):
        """
        Create a path within the targetdir
        """
        return os.path.join(self.folder, filename)

    def remove_targetdir(self):
        if os.path.exists(self.targetdir) and not self.is_custom_targetdir:
            shutil.rmtree(self.targetdir)
            return True
        return False

    def to_image_dim(self, x, dim):
        """
        Map to a image dimension
        """
        scaled_x = None
        if dim == 'path_x':
            # scale time index to the x axis of the path
            scaled_x = self.rects()['path'][2] * \
                (float(x) / float(self.max_x))
        if dim == 'path_y':
            # scale a frequency to the y axis of the path
            scaled_x = self.rects()['path'][3] - self.rects()['path'][3] * \
                (x - float(self.min_y)) / (float(self.max_y) - float(self.min_y))
        return scaled_x

    def cairo_draw_canvas(self):
        """
        Just a rectangle around the action
        """
        canvas_color = ColorTools.COLOR_3
        surface = cairo.ImageSurface(
            cairo.FORMAT_ARGB32,
            self.rects()['path'][2] + 2 * self.PADDING,
            self.rects()['path'][3] + 2 * self.PADDING
        )
        ctx = cairo.Context(surface)
        ctx.set_source_rgba(
            *ColorTools.to_rgba_source(canvas_color)
        )
        ctx.rectangle(
            0,
            0,
            self.rects()['path'][2] + 2 * self.PADDING,
            self.rects()['path'][3] + 2 * self.PADDING
        )
        ctx.stroke()
        return surface

    def cairo_draw_grid(self):
        """
        Draw the grid with all the notes.
        Very confusing but useful for debugging
        """
        surface = cairo.ImageSurface(
            cairo.FORMAT_ARGB32,
            self.rects()['path'][2] + 2 * self.PADDING,
            self.rects()['path'][3] + 2 * self.PADDING
        )
        ctx = cairo.Context(surface)
        ctx.set_source_rgba(
            *ColorTools.to_rgba_source(ColorTools.COLOR_3)
        )

        for note in NoteTools.note_range(self.min_note, self.max_note):
            note_scaled = NoteTools.note_to_midi(note) if \
                self.is_midi else NoteTools.note_to_freq(note)
            y = self.to_image_dim(note_scaled, 'path_y')
            ctx.move_to(0, y + self.PADDING)
            ctx.line_to(self.rects()['path'][2], y + self.PADDING)
        ctx.set_source_rgba(
            **ColorTools.to_rgba_source(ColorTools.COLOR_3)
        )
        ctx.stroke()
        return surface

    def cairo_draw_rects(self):
        """
        Draw semi transparent black rectangles pitch is not defined
        """
        surface = cairo.ImageSurface(
            cairo.FORMAT_ARGB32,
            self.rects()['path'][2] + 2 * self.PADDING,
            self.rects()['path'][3] + 2 * self.PADDING
        )
        ctx = cairo.Context(surface)
        for x, y in enumerate(self.stripped_samples):
            if y == self.no_value or y == 0.0:
                x1 = self.PADDING + self.to_image_dim(x - 0.5, 'path_x')
                x2 = self.PADDING + self.to_image_dim(x + 0.5, 'path_x')
                width = x2 - x1
                ctx.rectangle(
                    x1,
                    0,
                    width,
                    self.rects()['path'][3] + 2 * self.PADDING
                )
                ctx.set_source_rgba(
                    *ColorTools.to_rgba_source(ColorTools.TRANSPARENT_2)
                )
                ctx.fill()
        return surface

    def cairo_draw_circles(self):
        """
        Draw circles only where estamation is relyble
        """
        surface = cairo.ImageSurface(
            cairo.FORMAT_ARGB32,
            self.rects()['path'][2] + 2 * self.PADDING,
            self.rects()['path'][3] + 2 * self.PADDING
        )
        ctx = cairo.Context(surface)
        for x, y in enumerate(self.stripped_samples):
            if y != self.no_value and y != 0.0:
                x1 = self.PADDING + self.to_image_dim(x, 'path_x')
                y1 = self.PADDING + self.to_image_dim(y, 'path_y')
                ctx.arc(x1, y1, 8, 0, 2 * math.pi)
                ctx.set_source_rgba(
                    *ColorTools.to_rgba_source(ColorTools.COLOR_6)
                )
                ctx.fill()
        return surface

    def cairo_draw_histo_peeks(self, leaders=5):
        """
            Outline the most used notes from the histogram
            Very confusing but interesting
        """
        surface = cairo.ImageSurface(
            cairo.FORMAT_ARGB32,
            self.rects()['path'][2] + 2 * self.PADDING,
            self.rects()['path'][3] + 2 * self.PADDING
        )
        ctx = cairo.Context(surface)
        ctx.set_source_rgba(
            *ColorTools.to_rgba_source(ColorTools.COLOR_2)
        )
        histo = self.histogram[0]
        histo_indexes = np.argsort(histo)
        c = 0
        for note in histo_indexes[::-1]:
            if note > 12:
                y = self.to_image_dim(note, 'path_y')
                ctx.move_to(0, y + self.PADDING)
                ctx.line_to(self.rects()['path'][2], y + self.PADDING)
                c = c + 1
                if c > leaders:
                    break
        ctx.set_source_rgba(
            *ColorTools.to_rgba_source(ColorTools.COLOR_4)
        )
        ctx.stroke()
        return surface

    def cairo_draw_path(self):
        """
        Draw the path that connects the estimations
        """
        path_color = ColorTools.to_rgba_source(ColorTools.COLOR_4)
        surface = cairo.ImageSurface(
            cairo.FORMAT_ARGB32,
            self.rects()['path'][2] + 2 * self.PADDING,
            self.rects()['path'][3] + 2 * self.PADDING
        )
        ctx = cairo.Context(surface)
        ctx.set_source_rgba(*path_color)
        ctx.set_line_width(4)
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)
        for x, y in enumerate(self.stripped_samples):
            if y:
                x1 = self.PADDING + self.to_image_dim(
                    x,
                    'path_x'
                )
                y1 = self.PADDING + self.to_image_dim(y, 'path_y')
                ctx.line_to(x1, y1)
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)
        ctx.stroke()
        return surface

    def cairo_set_source(self, ctx, surface, x, y):
        """
        Add a surface to a context.
        """
        ctx.set_source_surface(surface, x, y)
        ctx.paint()

    def cairo_draw_background(self, ctx):
        """
        Draw the background
        the path, circle and everything else that does not move
        """
        self.cairo_set_source(
            ctx,
            self.cairo_draw_canvas(),
            self.rects()['path'][0],
            self.rects()['path'][1]
        )
        if self.DRAW_GRID:
            self.cairo_set_source(
                ctx,
                self.cairo_draw_grid(),
                self.rects()['path'][0],
                self.rects()['path'][1]
            )
        if self.DRAW_HISTOGRAM_PEEKS:
            self.cairo_set_source(
                ctx,
                self.cairo_draw_histo_peeks(),
                self.rects()['path'][0],
                self.rects()['path'][1]
            )
        self.cairo_set_source(
            ctx,
            self.cairo_draw_path(),
            self.rects()['path'][0],
            self.rects()['path'][1]
        )
        self.cairo_set_source(
            ctx,
            self.cairo_draw_circles(),
            self.rects()['path'][0],
            self.rects()['path'][1]
        )
        self.cairo_set_source(
            ctx,
            self.cairo_draw_text(),
            self.rects()['text'][0],
            self.rects()['text'][1]
        )
    
    def set_strip_samples(self):
        self.first_index, self.last_index = None, None
        for x, y in reversed(list(enumerate(self.samples))):
            if y:
                self.last_index = x + 1
                break
        for x, y in enumerate(self.samples):
            if y:
                self.first_index = x
                break
        self.stripped_samples = self.samples[self.first_index:self.last_index]
        self.max_x = self.stripped_samples.size

    def cairo_draw_text(self):
        surface_text = cairo.ImageSurface(
            cairo.FORMAT_ARGB32,
            self.rects()['text'][2], self.rects()['text'][3])
        ctx = cairo.Context(surface_text)
        ctx.set_source_rgba(*ColorTools.to_rgba_source(ColorTools.COLOR_8))
        ctx.set_font_size(80)
        ctx.select_font_face(
            "Lato",
            cairo.FONT_SLANT_NORMAL,
            cairo.FONT_WEIGHT_NORMAL
        )
        (x, y, width, height, dx, dy) = ctx.text_extents(self.data['text'])
        ctx.move_to(0,  height)
        ctx.show_text(self.data['text'])
        return surface_text

    
