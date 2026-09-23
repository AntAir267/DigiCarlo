# Where a point in a POV-Ray scene lands in the picture, for the cameras the
# scenes use. The program paints some things live (the calendar's date, the
# card's name, the green screen's text) onto flat surfaces in the renders;
# this finds the corners of those surfaces.
#
# POV-Ray is left-handed: x right, y up, z into the scene.
import math


def _sub(a, b): return tuple(x - y for x, y in zip(a, b))
def _dot(a, b): return sum(x * y for x, y in zip(a, b))
def _scale(a, k): return tuple(x * k for x in a)
def _norm(a): return _scale(a, 1.0 / math.sqrt(_dot(a, a)))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def rotate(p, r):
    """POV-Ray's `rotate <rx, ry, rz>`: about x, then y, then z, in degrees."""
    x, y, z = p
    a = math.radians(r[0])
    y, z = y * math.cos(a) - z * math.sin(a), y * math.sin(a) + z * math.cos(a)
    a = math.radians(r[1])
    x, z = x * math.cos(a) + z * math.sin(a), -x * math.sin(a) + z * math.cos(a)
    a = math.radians(r[2])
    x, y = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
    return (x, y, z)


def translate(p, t):
    return tuple(a + b for a, b in zip(p, t))


class Camera:
    """`location`, `look_at`, and either `angle` (perspective, horizontal
    field of view with `right x*image_width/image_height`) or `right` and
    `up` lengths (orthographic)."""

    def __init__(self, location, look_at, width, height, angle=None,
                 ortho=None):
        self.loc = location
        self.w, self.h = width, height
        d = _norm(_sub(look_at, location))
        self.right = _norm(_cross((0, 1, 0), d))
        self.up = _cross(d, self.right)
        self.dir = d
        self.angle = angle
        self.ortho = ortho
        if angle is not None:
            self.rlen = width / height
            self.dlen = 0.5 * self.rlen / math.tan(math.radians(angle) / 2)

    def project(self, p):
        v = _sub(p, self.loc)
        x, y, z = _dot(v, self.right), _dot(v, self.up), _dot(v, self.dir)
        if self.ortho:
            u, t = x / self.ortho[0], y / self.ortho[1]
        else:
            u = x / z * self.dlen / self.rlen
            t = y / z * self.dlen
        return ((u + 0.5) * self.w, (0.5 - t) * self.h)


def face(cam, w, h, z, transforms):
    """The corners of the face z of a box <0,0,..>-<w,h,..> after
    `transforms` ([('rotate', v) or ('translate', v)], in order), as the
    image on it sees them: top-left, top-right, bottom-right, bottom-left."""
    out = []
    for p in ((0, h, z), (w, h, z), (w, 0, z), (0, 0, z)):
        for kind, v in transforms:
            p = rotate(p, v) if kind == "rotate" else translate(p, v)
        out.append(cam.project(p))
    return out
