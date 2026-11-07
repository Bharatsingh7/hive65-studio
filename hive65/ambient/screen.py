"""Low-resolution screen capture for "movie mode".

Backends, best first:
    Windows   dxcam (DXGI desktop duplication) -> mss
    Hyprland  xdg-desktop-portal ScreenCast + GStreamer pipewiresrc -> grim
Frames come back as small float RGB arrays (rows x cols x 3, 0..1).
DRM-protected video (Netflix in a browser, ...) may capture as black.
"""
import json
import shutil
import subprocess
import sys
import threading
import time

import numpy as np

LINUX = sys.platform.startswith("linux")
WINDOWS = sys.platform == "win32"


def _downscale(rgb, size=(32, 10)):
    from PIL import Image
    img = Image.fromarray(rgb).resize(size, Image.BILINEAR)
    return np.asarray(img, dtype=float) / 255.0


def active_window_rect():
    """(left, top, right, bottom) of the focused window, or None."""
    try:
        if WINDOWS:
            import ctypes
            from ctypes import wintypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            rect = wintypes.RECT()
            DWMWA_EXTENDED_FRAME_BOUNDS = 9
            ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
                                                       ctypes.byref(rect), ctypes.sizeof(rect))
            return rect.left, rect.top, rect.right, rect.bottom
        if LINUX and shutil.which("hyprctl"):
            w = json.loads(subprocess.run(["hyprctl", "activewindow", "-j"],
                                          capture_output=True, text=True).stdout or "{}")
            if w.get("at"):
                (x, y), (cw, ch) = w["at"], w["size"]
                return x, y, x + cw, y + ch
    except Exception:
        pass
    return None


class _DxcamGrabber:
    def __init__(self):
        import dxcam
        self.cam = dxcam.create(output_color="BGRA")   # BGRA needs no OpenCV
        self.size = (self.cam.width, self.cam.height)
        self.last = None

    def grab(self, region=None):
        if region:
            w, h = self.size
            l, t, r, b = region
            region = (max(0, l), max(0, t), min(w, r), min(h, b))
            if region[2] - region[0] < 8 or region[3] - region[1] < 8:
                region = None
        frame = self.cam.grab(region=region) if region else self.cam.grab()
        if frame is None:          # screen unchanged since the last grab
            return self.last
        self.last = frame[..., [2, 1, 0]]
        return self.last


class _MssGrabber:
    def __init__(self):
        import mss
        self.sct = mss.mss()
        mon = self.sct.monitors[1]
        self.size = (mon["width"], mon["height"])

    def grab(self, region=None):
        mon = self.sct.monitors[1]
        box = ({"left": region[0], "top": region[1], "width": region[2] - region[0],
                "height": region[3] - region[1]} if region else mon)
        shot = self.sct.grab(box)
        return np.asarray(shot)[..., [2, 1, 0]]


class _GrimGrabber:
    """Wayland fallback: one screenshot per frame, scaled down by grim itself."""

    def __init__(self):
        if not shutil.which("grim"):
            raise RuntimeError("grim not installed")
        self.size = None

    def grab(self, region=None):
        from PIL import Image
        import io
        cmd = ["grim", "-s", "0.05", "-t", "ppm"]
        if region:
            l, t, r, b = region
            cmd += ["-g", f"{l},{t} {r - l}x{b - t}"]
        out = subprocess.run(cmd + ["-"], capture_output=True, timeout=2).stdout
        return np.asarray(Image.open(io.BytesIO(out)).convert("RGB"))


class _PortalGrabber:
    """Hyprland: ScreenCast portal -> PipeWire node -> GStreamer appsink (32x10).

    The portal shows a picker the first time; the restore token is saved so
    later runs reuse the choice.
    """

    def __init__(self):
        import gi
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
        from .portal import open_screencast
        Gst.init(None)
        fd, node = open_screencast()
        self.pipeline = Gst.parse_launch(
            f"pipewiresrc fd={fd} path={node} do-timestamp=true ! videoconvert ! videoscale ! "
            "video/x-raw,format=RGB,width=64,height=20 ! appsink name=sink max-buffers=1 drop=true")
        self.sink = self.pipeline.get_by_name("sink")
        self.pipeline.set_state(Gst.State.PLAYING)
        self.size = None

    def grab(self, region=None):
        sample = self.sink.emit("try-pull-sample", 50_000_000)
        if sample is None:
            return None
        buf = sample.get_buffer()
        ok, info = buf.map(1)  # Gst.MapFlags.READ
        try:
            return np.frombuffer(info.data, dtype=np.uint8).reshape(20, 64, 3).copy()
        finally:
            buf.unmap(info)


def make_grabber():
    order = [_DxcamGrabber, _MssGrabber] if WINDOWS else [_PortalGrabber, _GrimGrabber, _MssGrabber]
    errors = []
    for cls in order:
        try:
            return cls()
        except Exception as e:
            errors.append(f"{cls.__name__}: {e}")
    raise RuntimeError("no screen capture backend: " + "; ".join(errors))


class ScreenSampler(threading.Thread):
    """Keeps `latest` updated with a small RGB image of the screen (or window)."""

    def __init__(self, fps=24, region="screen"):
        super().__init__(daemon=True)
        self.fps, self.region = fps, region
        self.latest = None
        self.error = None
        self.stopped = threading.Event()
        self.start()

    def run(self):
        try:
            grabber = make_grabber()
        except Exception as e:
            self.error = str(e)
            return
        win_check = 0.0
        rect = None
        while not self.stopped.is_set():
            t0 = time.time()
            try:
                if self.region == "window" and t0 - win_check > 0.5:
                    rect, win_check = active_window_rect(), t0
                frame = grabber.grab(rect if self.region == "window" else None)
                if frame is not None:
                    self.latest = _downscale(np.ascontiguousarray(frame[..., :3]))
            except Exception as e:
                self.error = str(e)
                time.sleep(0.5)
            self.stopped.wait(max(0.0, 1 / self.fps - (time.time() - t0)))

    def stop(self):
        self.stopped.set()
