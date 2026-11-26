"""Find the streamer's camera overlay in a stream recording.

A facecam is a small face that stays put while the game moves around it. We
find that face, then snap a box to the overlay's border: the border is an edge
that is there in every frame, while the gameplay's edges move. Averaging the
edge strength over many frames makes the border stand out.
"""

from __future__ import annotations

import json
import logging
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path

log = logging.getLogger(__name__)

#: A facecam face is small; a full-frame camera shot is not a facecam stream.
MAX_FACE_HEIGHT = 0.3
#: The face must be in the same place in at least this share of sampled frames.
MIN_PRESENCE = 0.4
#: A border column/row must be this many times stronger than a typical one.
EDGE_CONTRAST = 2.5


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class StreamLayout:
    """Where the streamer's camera and the gameplay sit in a stream recording."""

    cam: Box
    game: Box
    #: "auto" when detected, "drawn" when the user drew the boxes.
    origin: str = "auto"


#: Per-source sidecar: the overlay doesn't move, so one layout serves every clip.
LAYOUT_FILE = "stream_layout.json"

#: The default gameplay box keeps the top of the frame. The bottom fifth holds
#: the game's own subtitles (one or two lines from ~83% down) and HUD clutter;
#: Chop Shop's captions replace the subtitles, so they are cropped away.
GAME_HEIGHT_FRACTION = 0.8


def default_game_box(width: int, height: int) -> Box:
    return Box(0, 0, width, int(height * GAME_HEIGHT_FRACTION) // 2 * 2)


def save_layout(media_dir: Path, layout: StreamLayout) -> None:
    (media_dir / LAYOUT_FILE).write_text(json.dumps(asdict(layout)), encoding="utf-8")


def load_layout(media_dir: Path) -> StreamLayout | None:
    path = media_dir / LAYOUT_FILE
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return StreamLayout(Box(**data["cam"]), Box(**data["game"]), data.get("origin", "auto"))


#: Camera feeds are landscape: anything outside this width/height is a mis-snap.
ASPECT_RANGE = (1.25, 2.1)


def detect_stream_facecam(video: Path, duration_s: float, *, windows: int = 5) -> Box | None:
    """Find the facecam by agreement across several stretches of the stream.

    One stretch can snap a side to the wrong line (a shelf behind the streamer,
    the minimap below the camera). The overlay itself never moves, so detect it
    in several places, drop boxes with a non-camera shape, and take each side's
    median.
    """
    span = min(40.0, duration_s / windows)
    boxes = [
        b
        for i in range(windows)
        if (b := detect_facecam(video, start_s=duration_s * i / windows, span_s=span))
        and ASPECT_RANGE[0] <= b.w / b.h <= ASPECT_RANGE[1]
    ]
    if not boxes:
        return None
    x0 = statistics.median(b.x for b in boxes)
    y0 = statistics.median(b.y for b in boxes)
    x1 = statistics.median(b.x + b.w for b in boxes)
    y1 = statistics.median(b.y + b.h for b in boxes)
    return Box(int(x0), int(y0), int(x1 - x0) // 2 * 2, int(y1 - y0) // 2 * 2)


def detect_facecam(
    video: Path, *, start_s: float = 0.0, span_s: float = 60.0, samples: int = 20
) -> Box | None:
    """Return the camera overlay's box in source pixels, or None if there isn't one.

    Uses OpenCV's Haar face detector rather than the MediaPipe landmarker the
    rest of reframing uses: a facecam face is often under 80px tall, below what
    the landmarker reliably finds, and Haar is fast enough to read each frame once.
    """
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        log.warning("Facecam detection skipped: %s", exc)
        return None

    detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    capture = cv2.VideoCapture(str(video))
    full_w = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    full_h = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if not full_w or not full_h:
        capture.release()
        return None
    # Work at half resolution: a quarter of the memory, and borders survive it.
    width, height = full_w // 2, full_h // 2

    faces: list[tuple[int, float, float, float, float]] = []  # (frame, cx, cy, w, h)
    edge_total = None
    read = 0
    for i in range(samples):
        capture.set(cv2.CAP_PROP_POS_MSEC, (start_s + span_s * i / samples) * 1000)
        ok, frame = capture.read()
        if not ok:
            continue
        read += 1
        gray = cv2.resize(
            cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (width, height), interpolation=cv2.INTER_AREA
        )
        del frame
        for x, y, w, h in detector.detectMultiScale(gray, 1.1, 6, minSize=(14, 14)):
            if h < MAX_FACE_HEIGHT * height:
                faces.append((i, x + w / 2, y + h / 2, float(w), float(h)))
        g = gray.astype(np.float32)
        pair = np.stack(
            [
                np.abs(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)),
                np.abs(cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)),
            ]
        )
        edge_total = pair if edge_total is None else edge_total + pair
    capture.release()
    if not faces or not read:
        return None

    # The facecam is the spot a face keeps showing up in; game characters wander.
    def steady_near(cx: float, cy: float) -> list:
        return [
            f for f in faces if abs(f[1] - cx) < 0.04 * width and abs(f[2] - cy) < 0.06 * height
        ]

    anchor = max(faces, key=lambda f: len({g[0] for g in steady_near(f[1], f[2])}))
    steady = steady_near(anchor[1], anchor[2])
    if len({f[0] for f in steady}) < MIN_PRESENCE * read:
        return None
    cx = statistics.median(f[1] for f in steady)
    cy = statistics.median(f[2] for f in steady)
    fw = statistics.median(f[3] for f in steady)
    fh = statistics.median(f[4] for f in steady)

    half = _snap_to_border(edge_total / read, cx, cy, fw, fh, width, height)
    box = Box(half.x * 2, half.y * 2, half.w * 2, half.h * 2)
    log.info("Facecam at %s.", box)
    return box


def _snap_to_border(edges, cx, cy, fw, fh, width, height) -> Box:
    """Grow outward from the face to the strongest fixed edge on each side."""
    # Fallback proportions for a head-and-shoulders camera when no border shows.
    left, right = cx - 2.2 * fw, cx + 2.2 * fw
    top, bottom = cy - 1.3 * fh, cy + 1.6 * fh

    if edges is not None:
        gx, gy = edges
        rows = slice(int(max(0, cy - fh)), int(min(height, cy + fh)))
        cols = slice(int(max(0, cx - fw)), int(min(width, cx + fw)))
        col_strength = gx[rows, :].mean(axis=0)  # vertical borders
        row_strength = gy[:, cols].mean(axis=1)  # horizontal borders
        left = _strongest(col_strength, cx - 0.7 * fw, cx - 6 * fw, default=left, edge=0)
        right = _strongest(col_strength, cx + 0.7 * fw, cx + 6 * fw, default=right, edge=width)
        top = _strongest(row_strength, cy - 0.7 * fh, cy - 4 * fh, default=top, edge=0)
        bottom = _strongest(row_strength, cy + 0.9 * fh, cy + 4 * fh, default=bottom, edge=height)

    x0, y0 = int(max(0, left)), int(max(0, top))
    x1, y1 = int(min(width, right)), int(min(height, bottom))
    return Box(x0, y0, (x1 - x0) // 2 * 2, (y1 - y0) // 2 * 2)


def _strongest(strength, near: float, far: float, *, default: float, edge: int) -> float:
    """Position of the strongest edge between near and far, else the frame edge or default."""
    lo, hi = sorted((int(near), int(far)))
    lo, hi = max(0, lo), min(len(strength) - 1, hi)
    if hi <= lo:
        return edge  # the search ran off the frame: the overlay touches the edge
    window = strength[lo : hi + 1]
    typical = float(sorted(window)[len(window) // 2]) or 1e-6
    peak = int(window.argmax())
    if window[peak] >= EDGE_CONTRAST * typical:
        return lo + peak
    # No border inside the search: if the search reached the frame edge, use it.
    return edge if (far <= 0 or far >= len(strength)) else default
