import json
import numpy as np

from PyQt5.QtCore import (pyqtProperty, pyqtSignal, pyqtSlot, QObject, QPoint,
                          QPointF)

from lib.dtypes import pixel_color, pixel_location
from lib.geometry import (distance, distance_point_to_line, inflate_rect,
                          vec2_sum)

__all__ = [
    "PixelGroup", "LinearPixelGroup", "RectangularPixelGroup",
    "CircularPixelGroup"
]


class Handle:
    """
    Represents a graphical handle used for manipulating objects

    TODO: these should be associated with properties in the parent class, so
    they can automatically update a property when moved, etc.
    """

    def __init__(self, parent, pos):
        self.parent = parent
        self.pos = pos
        self.hovering = False
        self.dragging = False
        self.drag_start_pos = None

    @property
    def pos(self):
        if self.parent.dragging:
            return vec2_sum(self._pos, self.parent.drag_delta)
        return self._pos

    @pos.setter
    def pos(self, p):
        self._pos = p

    def hit_test(self, pos, epsilon=25):
        if type(pos) == QPoint or type(pos) == QPointF:
            pos = pos.x(), pos.y()
        dist = distance(self.pos, pos)
        return 0 if (dist > epsilon) else dist


class PixelGroup(QObject):
    """
    A PixelGroup is a set of pixels that have some internal geometric ordering.
    For example, a linear array (LED strip), square array, or circular array.
    This class gets subclassed to define the shape-specific details.

    These classes handle the data model as well as UI interactivity (drag, etc).
    At some point it might make sense to split those two functions apart, but
    for now they are both here for simplicity.  Actually drawing the PixelGroup
    is done by painter methods in CanvasView.

    PixelGroups are each a single entity in the scene model (i.e. stored in the
    scene file) and a single widget to interact with in the canvas.

    Any scene can have zero or more PixelGroups, each with one or more pixels.

    PixelGroups are used for WYSIWYG editing/layout of scenes, but could also be
    used in the future as another piece of data for pattern generation.

    All locations are stored in scene coordinate space.
    LED addresses are (strand, offset) tuples.
    """

    def __init__(self, count, strand=0, offset=0):
        super(PixelGroup, self).__init__()

        # Properties accessible from QML
        self._count = count
        self._strand = strand
        self._offset = offset

        # GUI-related
        self.selected = False
        self.draw_bb = False
        self.hovering = False
        self.handles = []
        self.dragging = False
        self._drag_start_pos = None
        self._drag_delta = None

    changed = pyqtSignal()

    def __repr__(self):
        return "PixelGroup address (%d, %d)" % (self.strand, self.offset)

    @pyqtProperty(int, notify=changed)
    def count(self):
        return self._count

    @count.setter
    def count(self, val):
        if self._count != val:
            self._count = val
            self.pixel_locations = np.zeros(self._count, dtype=pixel_location)
            self.pixel_colors = np.zeros(self.count, dtype=pixel_color)

    @pyqtProperty(int, notify=changed)
    def strand(self):
        return self._strand

    @strand.setter
    def strand(self, val):
        if self._strand != val and val > 0:
            self._strand = val

    @pyqtProperty(int, notify=changed)
    def offset(self):
        return self._offset

    @offset.setter
    def offset(self, val):
        if self._offset != val and val > 0:
            self._offset = val

    @property
    def drag_delta(self):
        return self._drag_delta

    def bounding_box(self):
        """
        Returns a bounding box that encompasses the pixels in the group
        (x, y, width, height) where (x, y) are the upper-left coordinates.
        """
        raise NotImplementedError("Please override bounding_box()!")

    def hit_test(self, pos):
        """
        Returns True if pos is inside the graphical bounds of the group.
        The graphical bounds may be smaller (but not larger) than the bounding
        box.
        """
        raise NotImplementedError("Please override hit_test()!")

    def move_by(self, pos):
        """
        Translates the entire group by the delta (x, y) in scene space.
        """
        raise NotImplementedError("Please override move_by()!")

    def from_json(self, json):
        """
        Loads the PixelGroup data from a JSON dict
        """
        raise NotImplementedError("Please override from_json()!")

    def to_json(self):
        """
        Returns the PixelGroup data as a dict suitable for saving in JSON
        """
        raise NotImplementedError("Please override to_json()!")

    def on_drag_start(self, start_pos):
        raise NotImplementedError("Please override on_drag_start()!")

    def on_drag_move(self, delta_pos):
        raise NotImplementedError("Please override on_drag_move()!")

    def on_drag_end(self, delta_pos):
        raise NotImplementedError("Please override on_drag_end()!")

    def on_drag_cancel(self):
        raise NotImplementedError("Please override on_drag_cancel()!")

    def type(self):
        raise NotImplementedError("Please override type()!")


class LinearPixelGroup(PixelGroup):
    """
    Represents a linear array (strip) of evenly-spaced pixels.

    Defined by pixel count and start / end points (in scene-space units).
    The first pixel will overlap with the
    """

    def __init__(self, start=(0, 0), end=(0, 0), count=0,
                 strand=0, offset=0, json=None):

        super(LinearPixelGroup, self).__init__(count, strand, offset)
        if json is not None:
            self.from_json(json)
        else:
            self.start = start
            self.end = end
            self.count = count
            self.strand = strand
            self.offset = offset

        self.start_handle = Handle(self, self.start)
        self.end_handle = Handle(self, self.end)

        self._bounding_box = None
        self._update_geometry()

    changed = pyqtSignal()

    def __repr__(self):
        return ("LinearPixelGroup address (%s) start (%s) end (%s) count %d" %
                (self.address, self.start, self.end, self.count))

    @pyqtProperty(str, notify=changed)
    def type(self):
        return "linear"

    @property
    def start(self):
        if self._drag_delta is not None:
            return vec2_sum(self._start, self._drag_delta)
        return self._start

    @start.setter
    def start(self, val):
        self._start = val

    @property
    def end(self):
        if self._drag_delta is not None:
            return vec2_sum(self._end, self._drag_delta)
        return self._end

    @end.setter
    def end(self, val):
        self._end = val

    @pyqtSlot()
    def flip(self):
        temp = self.start
        self.start = self.end
        self.end = temp
        self._update_geometry()

    def from_json(self, json):
        self.start = tuple(json["start"])
        self.end = tuple(json["end"])
        self.count = json["count"]
        self.strand = json["strand"]
        self.offset = json["offset"]

    def to_json(self):
        d = {
            "type": "linear",
            "strand": self.strand,
            "offset": self.offset,
            "count": self.count,
            "start": self.start,
            "end": self.end
        }
        return d

    def _update_geometry(self):
        if self.count > 0:
            ox = (self.end[0] - self.start[0]) / self.count
            oy = (self.end[1] - self.start[1]) / self.count
            px, py = self.start[0], self.start[1]
            for i in range(self.count):
                self.pixel_locations[i] = (px, py)
                px += ox
                py += oy
        self._bounding_box = None

        # TODO: It would be nice if Handles updated automatically
        self.start_handle.pos = self.start
        self.end_handle.pos = self.end

    def bounding_box(self):
        if self._bounding_box is None:
            x1, y1 = self.start
            x2, y2 = self.end
            x, y = (min(x1, x2), min(y1, y2))
            self._bounding_box = (x, y, abs(x2 - x1), abs(y2 - y1))
            self._bounding_box = inflate_rect(self._bounding_box, 50)
        return self._bounding_box

    def hit_test(self, pos, epsilon=10):
        dist = distance_point_to_line(self.start, self.end, pos)
        hit = (dist <= epsilon)
        return dist if hit else 0

    def move_by(self, pos):
        self.start = vec2_sum(self.start, pos)
        self.end = vec2_sum(self.end, pos)
        self._update_geometry()

    def on_drag_start(self, start_pos):
        # TODO: This could be more smart if the Handles were more smart
        if self.start_handle.hit_test(start_pos):
            self.start_handle.drag_start_pos = self.start_handle.pos
            self.start_handle.dragging = True
        elif self.end_handle.hit_test(start_pos):
            self.end_handle.drag_start_pos = self.end_handle.pos
            self.end_handle.dragging = True
        else:
            self.dragging = True
            self._drag_start_pos = start_pos
            self._drag_delta = (0, 0)

    def on_drag_move(self, delta_pos):
        if self.start_handle.dragging:
            self.start = vec2_sum(self.start_handle.drag_start_pos, delta_pos)
            self.start_handle.pos = self.start
        elif self.end_handle.dragging:
            self.end = vec2_sum(self.end_handle.drag_start_pos, delta_pos)
            self.end_handle.pos = self.end
        else:
            self._drag_delta = delta_pos

    def on_drag_end(self, delta_pos):
        if self.dragging:
            self.dragging = False
            self._drag_start_pos = None
            self._drag_delta = None
            self.move_by(delta_pos)

        self.start_handle.dragging = False
        self.start_handle.drag_start_pos = None
        self.end_handle.dragging = False
        self.end_handle.drag_start_pos = None

    def on_drag_cancel(self):
        if self.start_handle.dragging:
            self.start = self.start_handle.drag_start_pos
            self.start_handle.dragging = False
            self.start_handle.drag_start_pos = None
            self.start_handle.pos = self.start
        elif self.end_handle.dragging:
            self.end = self.end_handle.drag_start_pos
            self.end_handle.dragging = False
            self.end_handle.drag_start_pos = None
            self.end_handle.pos = self.end
        else:
            self.dragging = False
            self._drag_start_pos = None
            self._drag_delta = None


class RectangularPixelGroup(PixelGroup):
    """
    Represents a rectanglar grid of evenly-spaced pixels.

    Defined by corners (start, end) and pixel count (rows, cols)
    """

    def __init__(self, start, end, rows, cols, address=None):
        super(RectangularPixelGroup, self).__init__(rows * cols, address)
        self.start = start
        self.end = end


class CircularPixelGroup(PixelGroup):
    """
    Represents a circular array of evenly-spaced pixels.

    Defined by pixel count, radius, start angle, and end angle (meaning that it
    can define either a circle or an arc).  For a circle, start and end angle
    should be the same.  For an arc, the pixels will be placed clockwise from
    the start angle to the end angle.  Spacing will be calculated based on the
    other parameters.
    """

    def __init__(self, center, count, radius,
                 start_angle, end_angle, address=None):
        super(CircularPixelGroup, self).__init__(count, address)
        self.radius = radius
        self.start_angle = start_angle
        self.end_angle = end_angle
        self.center = center


class ArbitraryPixelGroup(PixelGroup):
    """
    Represents an arbitrary set of pixels that should be logically grouped
    together even if they don't form a regular geometric shape.

    Until there is a GUI for forming AribtraryPixelGroups out of individual
    pixels, these must be loaded in from a file.
    """

    def __init__(self, count, address=None):
        super(ArbitraryPixelGroup, self).__init__(count, address)
