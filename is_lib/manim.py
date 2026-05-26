from manim import Scene, Dot, NumberPlane, VMobject, LineJointType
from manim import Text, MoveAlongPath, VGroup, Line, Axes, Triangle, Rectangle
from manim import linear, config, Write, Transform
from manim import RED, GREEN, BLUE, PINK, TEAL
from manim import LEFT, RIGHT, UP, DOWN, UL, DR
import numpy as np
import math

COLORS = {
    "BACKGROUND": "#1A1E22",
    "PATH": "#425265",
    "POINTS": "#459DCC",
    "SUBTEXT": "#BCADE3",
    "TEXT": "#F1F1F1"
}


class MoveAlongPointPath(MoveAlongPath):
    """Make one mobject move along the path of another mobject.

    .. manim:: MoveAlongPathExample

        class MoveAlongPathExample(Scene):
            def construct(self):
                d1 = Dot().set_color(ORANGE)
                l1 = Line(LEFT, RIGHT)
                l2 = VMobject()
                self.add(d1, l1, l2)
                l2.add_updater(lambda x: x.become(Line(LEFT, d1.get_center()).set_color(ORANGE)))
                self.play(MoveAlongPath(d1, l1), rate_func=linear)
    """

    def __init__(
        self,
        points,
        active_points,
        *args,
        **kwargs,
    ) -> None:
        self.points = points
        self.active_points = active_points
        super().__init__(*args, **kwargs)

    def is_active(self, point):
        for active_point in self.active_points:
            if np.array_equal(point, active_point):
                return True
        return False

    def interpolate_mobject(self, alpha: float) -> None:
        point_index = math.ceil(alpha*len(self.points))
        point = self.points[point_index-1]
        self.mobject.move_to(point)


class ISPlot(Scene):
    data = None

    MIN_X, MAX_X = -7, 7
    WIDTH = MAX_X - MIN_X
    MIN_Y, MAX_Y = -3, 2
    HEIGHT = MAX_Y - MIN_Y
    PADDING_X = 0 * WIDTH
    PADDING_Y = 0 * HEIGHT

    def get_frame_width(self):
        return config.frame_width

    def get_frame_height(self):
        return config.frame_height

    def step_x(self):
        return (self.WIDTH - self.PADDING_X) / (len(self.data['samples']))

    def text(self):
        return self.data['text']

    def subtext(self):
        return self.data['subtext'] if 'subtext' in self.data else ""

    def credits(self):
        return self.data['credits']

    def min_y(self):
        return float(self.data['min_y'])

    def max_y(self):
        return float(self.data['max_y'])

    def samples(self):
        return float(self.data['max_y'])

    def get_duration(self):
        """"
        Duration in seconds
        """
        return float(self.data['duration'])

    def get_point_duration(self):
        """"
        Duration in seconds
        """
        return float(self.data['hop']) / float(self.data['samplerate'])

    def step_y(self):
        return (self.HEIGHT - self.PADDING_Y) / (self.max_y() - self.min_y())

    def get_x(self, x):
        return self.PADDING_X / 2 + x * self.step_x() + self.MIN_X

    def get_y(self, y):
        if y is None:
            y = self.min_y()
        return self.PADDING_Y / 2 + (y - self.min_y()) * self.step_y() + self.MIN_Y

    def print_data(self):
        print(self.data['samples'])

    def references(self):
        number_plane = NumberPlane(
            background_line_style={
                "stroke_color": TEAL,
                "stroke_width": 1,
                "stroke_opacity": 0.3
            },
            axis_config={
                "stroke_width": 0,
            }
        )

        self.add(number_plane)
        bottom_left = Dot(np.array([self.MIN_X, self.MIN_Y, 0]),
                          radius=.1, color=RED)
        top_left = Dot(np.array([self.MIN_X, self.MAX_Y, 0]),
                       radius=.1, color=BLUE)
        top_right = Dot(np.array([self.MAX_X, self.MAX_Y, 0]),
                        radius=.1, color=GREEN)
        bottom_right = Dot(np.array([self.MAX_X, self.MIN_Y, 0]),
                           radius=.1, color=PINK)
        self.add(
            top_right,
            bottom_right,
            top_left,
            bottom_left
        )

    def draw_section(self):
        self.samples = np.array(self.data['samples'])
        points = []
        active_points = []
        dots = []
        # connected paths
        paths = []
        path = None
        last = None
        current = None
        for index, item in enumerate(self.samples):
            x, y = self.get_x(index), self.get_y(item)
            point = np.array([x, y, 0])
            current = point if item is not None else None
            points.append(point)
            dot = Dot(point, radius=0.06, color=COLORS["POINTS"])
            dots.append(dot)
            if current is not None:
                self.add(dot)
                active_points.append(point)
                if last is None:
                    path = []
                    paths.append(path)
                path.append(current)
                last = current
            else:
                last = None
        for p in paths:
            path = VMobject()
            path.set_points_as_corners(p)
            path.set_color(COLORS["PATH"])
            path.joint_type = LineJointType.ROUND
            self.add(path)

        guide = VMobject()
        guide.set_points_as_corners(points)

        text = Text(
            self.text(),
            color=COLORS["TEXT"],
            font_size=68,
            font='Futura'
        )
        subtext1 = Text(
            "How to say",
            color=COLORS["SUBTEXT"],
            font_size=24,
            font='Futura'
        )
        subtext2 = Text(
            f"in {self.language} with intonation!",
            color=COLORS["SUBTEXT"],
            font_size=24,
            font='Futura'
        )
        credits = Text(
            "#SayItRight #SeeItSayIt",
            color=COLORS["SUBTEXT"],
            font_size=14,
            font='Futura'
        )
        text_group = VGroup(*[subtext1, text, subtext2])
        text_group.arrange(DOWN, center=False, aligned_edge=LEFT, buff=0.1)
        text_group.to_corner(UL)
        credits.to_corner(DR)
        self.add(text_group)
        self.add(credits)
        self.add_arrow()
        # animation
        self.add_animation_1(points, active_points, guide, gain=1)
        self.add_countdown()
        self.add_animation_1(points, active_points, guide, gain=-30)

    def add_countdown(self):
        rect1 = Rectangle(
            width=self.get_frame_width(),
            height=self.get_frame_height(),
            color=COLORS["BACKGROUND"]
        )
        rect1.set_opacity(0.3)
        self.add(rect1)
        number = Text("3").set_color(COLORS["TEXT"]).scale(3)
        self.add(number)
        help = Text("Your Turn!").set_color(COLORS["SUBTEXT"]).scale(2)
        self.add(help)
        help.next_to(number, UP)
        help.shift(UP)
        for i in range(3, 0, -1):
            if i != -1:
                self.play(Transform(number,
                                    Text(str(i)).set_color(COLORS["TEXT"]).scale(3)), run_time=0.01)
                self.wait()
        self.remove(number)
        self.remove(help)
        self.remove(rect1)

    def add_axis(self):
        x_start = self.get_x(0)
        x_end = self.get_x(len(self.data['samples']))
        y_start = self.get_y(self.min_y())
        y_end = self.get_x(self.max_y())
        ax = Axes(
            x_range=[x_start, x_end, 1],
            y_range=[y_start, y_end, 1],
        )
        self.add(ax)

    def add_arrow(self):
        start_y = np.array(
            [self.get_x(0), self.get_y(self.min_y()) - 0.2, 0.0]
        )
        end_y = np.array(
            [self.get_x(0), self.get_y(self.max_y()) - 0.2, 0.0]
        )
        end_x = np.array(
            [self.get_x(len(self.samples)), self.get_y(self.min_y()), 0.0]
        )
        arrow_y = Line(
            start=start_y,
            end=end_y,
            color=COLORS["PATH"],
            stroke_width=1
        )
        arrow_x = Line(
            start=start_y,
            end=end_x,
            color=COLORS["PATH"],
            stroke_width=1
        )
        triangle = Triangle(
            stroke_width=1, color=COLORS["PATH"]
        ).scale(0.1).move_to(end_y)
        self.add(triangle)
        t1 = Text("Pitch (Hz)", color=COLORS["SUBTEXT"], font_size=14)
        text1 = VGroup(t1).arrange(DOWN, aligned_edge=LEFT)
        text1.next_to(arrow_y, RIGHT)
        text1.shift(UP*2)
        self.add(arrow_x)
        self.add(text1)
        self.add(arrow_y)

    def add_animation_1(self, points, active_points, path, gain):
        d1 = Dot(
            points[0],
            radius=0.12
        ).set_color(COLORS["TEXT"])
        self.add(d1)
        self.add_sound(self.sound, gain=gain)
        anim = MoveAlongPointPath(points, active_points, d1, path)
        self.play(
            anim,
            rate_func=linear,
            run_time=self.get_duration()
        )
        self.wait()
        self.remove(d1)
        self.remove(self.sound)

    def construct(self):
        if self.audios is None:
            raise Exception("No audios found")
        # self.references()
        for audio in self.audios:
            self.clear()
            self.camera.background_color = COLORS["BACKGROUND"]
            self.sound = audio.file.path
            self.language = audio.language.name
            self.data = audio.analysis.data
            if "text" not in self.data:
                self.data["text"] = audio.get_text()
            if "credits" not in self.data:
                self.data["credits"] = audio.get_credits()
            self.draw_section()
            self.next_section(f"audio-{audio.id}")
