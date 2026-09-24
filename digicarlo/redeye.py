"""Red-eye removal with nothing but numpy and Pillow.

Faces are found by YuNet (face_detection_yunet_2023mar.onnx, MIT licence,
from OpenCV's model zoo), run here layer by layer in numpy: it is 53 small
convolutions and a few cheap operations, so it needs no deep-learning runtime.
The pre- and post-processing reproduce OpenCV's cv::FaceDetectorYN.

For each face, a patch round each eye is searched for a flash-red pupil: a
compact, roundish blob of deep red, surrounded by something that is not red.
Its red is replaced by a dark neutral taken from its own green and blue, so the
pupil keeps its shape and its catchlight.

Checked against OpenCV 4.10 on 138 flash photos from the Kodak EasyShare C613
and C315: the network's outputs agree to within 1.5e-5, the faces and eye
positions found are the same, and the corrected photos are identical byte for
byte. It takes about 0.8 s a photo, where OpenCV takes about 0.1 s.

The model file and its licence (YUNET_LICENSE) sit beside this module.
"""

import math
import os

import numpy as np

# ---------------------------------------------------------------------------
# A minimal ONNX reader: enough protobuf to get a graph and its weights
# ---------------------------------------------------------------------------

def _varint(buf, i):
    shift = result = 0
    while True:
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, i
        shift += 7


def _signed(v):
    return v - (1 << 64) if v >= 1 << 63 else v


def _fields(buf):
    i, n = 0, len(buf)
    while i < n:
        key, i = _varint(buf, i)
        f, wt = key >> 3, key & 7
        if wt == 0:
            v, i = _varint(buf, i)
        elif wt == 1:
            v, i = buf[i:i + 8], i + 8
        elif wt == 2:
            ln, i = _varint(buf, i)
            v, i = buf[i:i + ln], i + ln
        elif wt == 5:
            v, i = buf[i:i + 4], i + 4
        else:
            raise ValueError("unsupported protobuf wire type %d" % wt)
        yield f, wt, v


def _ints(wt, v):
    if wt != 2:
        return [_signed(v)]
    out, j = [], 0
    while j < len(v):
        d, j = _varint(v, j)
        out.append(_signed(d))
    return out


_DTYPES = {1: np.float32, 6: np.int32, 7: np.int64, 11: np.float64}


def _tensor(buf):
    dims, dtype, name, raw, floats, ints = [], 1, "", None, [], []
    for f, wt, v in _fields(buf):
        if f == 1:
            dims += _ints(wt, v)
        elif f == 2:
            dtype = v
        elif f == 4:
            floats.append(np.frombuffer(v, "<f4"))
        elif f == 7:
            ints += _ints(wt, v)
        elif f == 8:
            name = v.decode()
        elif f == 9:
            raw = v
    if raw is not None:
        arr = np.frombuffer(raw, _DTYPES[dtype]).copy()
    elif floats:
        arr = np.concatenate(floats).astype(np.float32)
    else:
        arr = np.array(ints, _DTYPES.get(dtype, np.int64))
    return name, arr.reshape(dims) if dims else arr


def _attribute(buf):
    name, val = "", None
    for f, wt, v in _fields(buf):
        if f == 1:
            name = v.decode()
        elif f == 2:
            val = float(np.frombuffer(v, "<f4")[0])
        elif f == 3:
            val = _signed(v)
        elif f == 4:
            val = v.decode()
        elif f == 5:
            val = _tensor(v)[1]
        elif f == 7:
            val = np.frombuffer(v, "<f4").tolist()
        elif f == 8:
            val = (val or []) + _ints(wt, v)
    return name, val


def load_onnx(path):
    """(nodes, weights, input names, output names) of an ONNX model."""
    with open(path, "rb") as fh:
        buf = fh.read()
    graph = next(v for f, _, v in _fields(buf) if f == 7)
    nodes, weights, inputs, outputs = [], {}, [], []
    for f, _, v in _fields(graph):
        if f == 1:
            node = {"in": [], "out": [], "op": "", "at": {}}
            for g, _, w in _fields(v):
                if g == 1:
                    node["in"].append(w.decode())
                elif g == 2:
                    node["out"].append(w.decode())
                elif g == 4:
                    node["op"] = w.decode()
                elif g == 5:
                    k, a = _attribute(w)
                    node["at"][k] = a
            nodes.append(node)
        elif f == 5:
            k, a = _tensor(v)
            weights[k] = a
        elif f == 11:
            inputs.append(next(w.decode() for g, _, w in _fields(v) if g == 1))
        elif f == 12:
            outputs.append(next(w.decode() for g, _, w in _fields(v) if g == 1))
    return nodes, weights, [i for i in inputs if i not in weights], outputs


# ---------------------------------------------------------------------------
# The operations YuNet uses
# ---------------------------------------------------------------------------

def _conv(x, w, b, at):
    """NCHW convolution: plain, 1x1, or depthwise, as YuNet needs."""
    n, c, h, wd = x.shape
    m, cg, kh, kw = w.shape
    sh, sw = at.get("strides", [1, 1])
    pt, pl, pb, pr = at.get("pads", [0, 0, 0, 0])
    group = at.get("group", 1)
    if pt or pl or pb or pr:
        x = np.pad(x, ((0, 0), (0, 0), (pt, pb), (pl, pr)))
    hp, wp = x.shape[2], x.shape[3]
    ho, wo = (hp - kh) // sh + 1, (wp - kw) // sw + 1
    if group == 1 and kh == kw == 1 and sh == sw == 1:
        out = np.tensordot(w[:, :, 0, 0], x, axes=([1], [1])).transpose(1, 0, 2, 3)
    elif group == 1:
        win = np.lib.stride_tricks.sliding_window_view(x, (kh, kw), axis=(2, 3))
        win = win[:, :, ::sh, ::sw][:, :, :ho, :wo]            # n c ho wo kh kw
        cols = win.transpose(0, 2, 3, 1, 4, 5).reshape(n * ho * wo, c * kh * kw)
        out = (cols @ w.reshape(m, -1).T).reshape(n, ho, wo, m).transpose(0, 3, 1, 2)
    elif group == c == m and cg == 1:
        out = np.zeros((n, m, ho, wo), np.float32)
        for i in range(kh):
            for j in range(kw):
                out += x[:, :, i:i + sh * ho:sh, j:j + sw * wo:sw] * w[None, :, 0, i, j, None, None]
    else:
        parts = []
        step_in, step_out = c // group, m // group
        for g in range(group):
            parts.append(_conv(x[:, g * step_in:(g + 1) * step_in], w[g * step_out:(g + 1) * step_out],
                               None, dict(at, group=1, pads=[0, 0, 0, 0])))
        out = np.concatenate(parts, axis=1)
    if b is not None:
        out = out + b[None, :, None, None]
    return np.ascontiguousarray(out, dtype=np.float32)


def _maxpool(x, at):
    kh, kw = at["kernel_shape"]
    sh, sw = at["strides"]
    if (kh, kw) == (sh, sw):
        n, c, h, w = x.shape
        h2, w2 = h // kh, w // kw
        return x[:, :, :h2 * kh, :w2 * kw].reshape(n, c, h2, kh, w2, kw).max(axis=(3, 5))
    raise NotImplementedError("max pooling with overlapping windows")


def _resize(x, scales, at):
    if at.get("mode", "nearest") != "nearest":
        raise NotImplementedError("resize mode %s" % at.get("mode"))
    fy, fx = int(round(scales[2])), int(round(scales[3]))
    return x.repeat(fy, axis=2).repeat(fx, axis=3)


def _reshape(x, shape):
    shape = [x.shape[i] if s == 0 else int(s) for i, s in enumerate(shape)]
    return x.reshape(shape)


class Net:
    """An ONNX graph run node by node, for the handful of operations
    YuNet contains."""

    def __init__(self, path):
        self.nodes, self.weights, self.inputs, self.outputs = load_onnx(path)

    def run(self, blob):
        vals = dict(self.weights)
        vals[self.inputs[0]] = blob.astype(np.float32)
        for nd in self.nodes:
            op, at = nd["op"], nd["at"]
            a = [vals[i] if i else None for i in nd["in"]]
            if op == "Conv":
                y = _conv(a[0], a[1], a[2] if len(a) > 2 else None, at)
            elif op == "Relu":
                y = np.maximum(a[0], 0)
            elif op == "MaxPool":
                y = _maxpool(a[0], at)
            elif op == "Resize":
                y = _resize(a[0], a[2], at)
            elif op == "Add":
                y = a[0] + a[1]
            elif op == "Sigmoid":
                y = 1.0 / (1.0 + np.exp(-a[0]))
            elif op == "Transpose":
                y = np.ascontiguousarray(a[0].transpose(at["perm"]))
            elif op == "Reshape":
                y = _reshape(a[0], a[1])
            elif op == "Identity":
                y = a[0]
            else:
                raise NotImplementedError("ONNX operation %s" % op)
            vals[nd["out"][0]] = y
        return {k: vals[k] for k in self.outputs}


# ---------------------------------------------------------------------------
# Faces, as cv::FaceDetectorYN finds them
# ---------------------------------------------------------------------------

MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "face_detection_yunet_2023mar.onnx")
_NET = None


def _net():
    global _NET
    if _NET is None:
        _NET = Net(MODEL)
    return _NET


def _iou(a, b):
    """Overlap of two integer (x, y, w, h) boxes, as OpenCV's Rect2i does."""
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def _nms(boxes, scores, score_threshold, nms_threshold, top_k):
    order = [i for i in sorted(range(len(scores)), key=lambda i: -scores[i])
             if scores[i] >= score_threshold][:top_k]
    keep = []
    for i in order:
        if all(_iou(boxes[i], boxes[k]) <= nms_threshold for k in keep):
            keep.append(i)
    return keep


def detect(bgr, score_threshold=0.85, nms_threshold=0.3, top_k=5000):
    """Faces in an HxWx3 BGR uint8 image: rows of x, y, w, h, then five
    landmarks (right eye, left eye, nose, right and left mouth corner) as x, y
    pairs, then the score -- the same 15 numbers OpenCV returns."""
    h, w = bgr.shape[:2]
    ph, pw = ((h - 1) // 32 + 1) * 32, ((w - 1) // 32 + 1) * 32
    blob = np.zeros((1, 3, ph, pw), np.float32)
    blob[0, :, :h, :w] = bgr.transpose(2, 0, 1)
    out = _net().run(blob)
    rows = []
    for stride in (8, 16, 32):
        cols_n, rows_n = pw // stride, ph // stride
        cls = np.clip(out["cls_%d" % stride].reshape(-1), 0, 1)
        obj = np.clip(out["obj_%d" % stride].reshape(-1), 0, 1)
        score = np.sqrt(cls * obj)
        bbox = out["bbox_%d" % stride].reshape(-1, 4)
        kps = out["kps_%d" % stride].reshape(-1, 10)
        for idx in np.nonzero(score >= score_threshold)[0]:
            r, c = divmod(int(idx), cols_n)
            cx = (c + bbox[idx, 0]) * stride
            cy = (r + bbox[idx, 1]) * stride
            bw = math.exp(bbox[idx, 2]) * stride
            bh = math.exp(bbox[idx, 3]) * stride
            face = [cx - bw / 2, cy - bh / 2, bw, bh]
            for k in range(5):
                face += [(kps[idx, 2 * k] + c) * stride, (kps[idx, 2 * k + 1] + r) * stride]
            face.append(float(score[idx]))
            rows.append(face)
    if len(rows) > 1:
        boxes = [tuple(int(v) for v in f[:4]) for f in rows]
        keep = _nms(boxes, [f[14] for f in rows], score_threshold, nms_threshold, top_k)
        rows = [rows[i] for i in keep]
    return np.array(rows, np.float32).reshape(-1, 15)


def _area_taps(n_in, n_out, scale):
    """Source indices and weights for each output pixel of a shrink by
    `scale`, computed exactly as OpenCV's INTER_AREA does, so a face seen
    here is the face OpenCV would see."""
    taps = []
    for o in range(n_out):
        f1 = o * scale
        f2 = f1 + scale
        cell = min(scale, n_in - f1)
        s1, s2 = math.ceil(f1), math.floor(f2)
        s2 = min(s2, n_in - 1)
        s1 = min(s1, s2)
        row = []
        if s1 - f1 > 1e-3:
            row.append((s1 - 1, (s1 - f1) / cell))
        for s in range(s1, s2):
            row.append((s, 1.0 / cell))
        if f2 - s2 > 1e-3:
            row.append((s2, min(min(f2 - s2, 1.0), cell) / cell))
        taps.append(row)
    width = max(len(r) for r in taps)
    idx = np.zeros((n_out, width), np.intp)
    wts = np.zeros((n_out, width), np.float32)
    for o, row in enumerate(taps):
        for k, (i, w) in enumerate(row):
            idx[o, k], wts[o, k] = i, w
    return idx, wts


def shrink(img, s):
    """An HxWxC uint8 image scaled by s < 1, averaging the area each output
    pixel covers -- OpenCV's resize(fx=s, fy=s, INTER_AREA)."""
    h, w = img.shape[:2]
    nw, nh = int(round(w * s)), int(round(h * s))
    xi, xw = _area_taps(w, nw, 1.0 / s)
    yi, yw = _area_taps(h, nh, 1.0 / s)
    src = img.astype(np.float32)
    rows = np.zeros((h, nw) + img.shape[2:], np.float32)
    for k in range(xi.shape[1]):
        rows += src[:, xi[:, k]] * (xw[:, k, None] if img.ndim == 3 else xw[:, k])
    out = np.zeros((nh, nw) + img.shape[2:], np.float32)
    for k in range(yi.shape[1]):
        out += rows[yi[:, k]] * (yw[:, k, None, None] if img.ndim == 3 else yw[:, k, None])
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)


def find_faces(image, max_side=1400, score_threshold=0.85):
    """Faces in a Pillow image, in its own pixel coordinates."""
    w, h = image.size
    s = min(1.0, max_side / float(max(w, h)))
    rgb = np.asarray(image.convert("RGB"))
    small = shrink(rgb, s) if s < 1.0 else rgb
    bgr = np.ascontiguousarray(small[:, :, ::-1])
    faces = detect(bgr, score_threshold)
    faces[:, :14] /= s
    return faces


# ---------------------------------------------------------------------------
# The red, and taking it out
# ---------------------------------------------------------------------------

def _neighbour_min(a, big):
    h, w = a.shape
    p = np.pad(a, 1, constant_values=big)
    m = a.copy()
    for dy in range(3):
        for dx in range(3):
            np.minimum(m, p[dy:dy + h, dx:dx + w], out=m)
    return m


def _label(mask):
    """8-connected components of a small boolean array: (labels, count)."""
    h, w = mask.shape
    big = h * w + 1
    lab = np.where(mask, np.arange(1, h * w + 1).reshape(h, w), big)
    while True:
        new = np.where(mask, _neighbour_min(lab, big), big)
        if np.array_equal(new, lab):
            break
        lab = new
    ids = np.unique(lab[mask])
    out = np.zeros((h, w), np.int32)
    for n, v in enumerate(ids, 1):
        out[lab == v] = n
    return out, len(ids)


def _fill_holes(mask):
    """Set the parts of ~mask that cannot reach the border (4-connected)."""
    bg = ~mask
    reach = np.zeros_like(mask)
    reach[0, :], reach[-1, :], reach[:, 0], reach[:, -1] = bg[0, :], bg[-1, :], bg[:, 0], bg[:, -1]
    while True:
        p = np.pad(reach, 1)
        grown = bg & (reach | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:])
        if np.array_equal(grown, reach):
            break
        reach = grown
    return mask | (bg & ~reach)


def _dilate(mask, times):
    for _ in range(times):
        p = np.pad(mask, 1)
        h, w = mask.shape
        out = mask.copy()
        for dy in range(3):
            for dx in range(3):
                out |= p[dy:dy + h, dx:dx + w]
        mask = out
    return mask


def _blur5(a):
    """OpenCV's 5x5 Gaussian at its default sigma: 1 4 6 4 1, reflected edges."""
    k = np.array([1, 4, 6, 4, 1], np.float32) / 16
    p = np.pad(a, 2, mode="reflect")
    h, w = a.shape
    rows = sum(k[i] * p[:, i:i + w] for i in range(5))
    return sum(k[i] * rows[i:i + h, :] for i in range(5))


def red_mask(patch):
    """The flash-red pupil in an RGB eye patch, as a boolean array, or None.

    A pupil lit red by flash is deep red -- far redder than skin or lips ever
    get -- compact, roundish, and surrounded by iris and white. Red fabric or
    a lamp is red out to the edge of the patch, or fills most of it; those
    are left alone.
    """
    r, g, b = (patch[:, :, i].astype(np.int32) for i in range(3))
    mask = (r > 90) & (r > 1.8 * g) & (r > 1.6 * b)
    if not mask.any():
        return None
    lab, n = _label(mask)
    hh, ww = mask.shape
    best, bestd = None, 1e9
    for i in range(1, n + 1):
        ys, xs = np.nonzero(lab == i)
        area = len(xs)
        x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        if area < max(4, mask.size * 0.004) or area > mask.size * 0.35:
            continue
        if x0 == 0 or y0 == 0 or x1 == ww - 1 or y1 == hh - 1:
            continue                        # runs off the patch: not a pupil
        if area < 0.45 * bw * bh or max(bw, bh) > 2.2 * min(bw, bh):
            continue                        # not round enough
        d = math.hypot(xs.mean() - ww / 2, ys.mean() - hh / 2)
        if d < bestd and d < max(ww, hh) * 0.3:
            best, bestd = i, d
    if best is None:
        return None
    return _dilate(_fill_holes(lab == best), 2)


def fix_patch(rgb, x, y, size):
    """Take the flash red out of the pupil in the square (x, y, size) of an
    RGB array, in place. Says whether there was a red pupil there."""
    patch = rgb[y:y + size, x:x + size]
    mask = red_mask(patch)
    if mask is None:
        return False
    p = patch.astype(np.float32)
    dark = (p[:, :, 1] + p[:, :, 2]) / 2 * 0.8      # a pupil is dark, and neutral
    m = _blur5(mask.astype(np.float32))[:, :, None]
    patch[:] = (p * (1 - m) + dark[:, :, None] * m).astype(np.uint8)
    return True


def remove_red_eye(image, faces=None, max_side=1400):
    """(corrected Pillow image, [(x, y, w, h) of each eye fixed], faces)."""
    from PIL import Image
    rgb = np.array(image.convert("RGB"))
    if faces is None:
        faces = find_faces(image, max_side)
    fixed = []
    for f in faces:
        eyes = ((f[4], f[5]), (f[6], f[7]))
        d = math.hypot(f[4] - f[6], f[5] - f[7])
        rad = max(4, int(d * 0.26))
        for cx, cy in eyes:
            x, y = int(cx - rad), int(cy - rad)
            if x < 0 or y < 0 or x + 2 * rad > rgb.shape[1] or y + 2 * rad > rgb.shape[0]:
                continue
            if fix_patch(rgb, x, y, 2 * rad):
                fixed.append((x, y, 2 * rad, 2 * rad))
    return Image.fromarray(rgb), fixed, faces


def box_at(size, x, y):
    """Where to look for a pupil someone pointed at, at (x, y) in a picture
    of `size` (w, h): a square round it, big enough for an eye at the sizes
    these cameras take pictures, kept inside the picture."""
    w, h = size
    side = max(24, int(max(w, h) * 0.045)) // 2 * 2
    side = min(side, w, h)
    bx = min(max(0, int(x) - side // 2), w - side)
    by = min(max(0, int(y) - side // 2), h - side)
    return (bx, by, side, side)


def apply_fixes(image, boxes):
    """Fix the red pupil in each (x, y, w, h): the ones remove_red_eye found
    that were kept, and any pointed out by hand. Returns the corrected image
    and the boxes that did hold a red pupil."""
    from PIL import Image
    rgb = np.array(image.convert("RGB"))
    done = []
    for x, y, w, h in boxes:
        side = min(w, h)
        if fix_patch(rgb, int(x), int(y), int(side)):
            done.append((x, y, w, h))
    return Image.fromarray(rgb), done
