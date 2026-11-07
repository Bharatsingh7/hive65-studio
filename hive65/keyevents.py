"""Global key-press listener for typing-reactive effects.

Windows/macOS: pynput low-level hook (virtual-key codes match KB.ini).
Linux: evdev on the Hive 65's own keyboard device (needs the udev rule).
"""
import queue
import sys
import threading

# Linux evdev key name -> Windows virtual-key code, so both share Layout.by_vk.
_EVDEV_TO_VK = {
    "KEY_ESC": 0x1B, "KEY_TAB": 0x09, "KEY_CAPSLOCK": 0x14, "KEY_LEFTSHIFT": 0xA0,
    "KEY_RIGHTSHIFT": 0xA1, "KEY_LEFTCTRL": 0xA2, "KEY_RIGHTCTRL": 0xA3,
    "KEY_LEFTMETA": 0x5B, "KEY_LEFTALT": 0xA4, "KEY_RIGHTALT": 0xA5, "KEY_SPACE": 0x20,
    "KEY_BACKSPACE": 0x08, "KEY_ENTER": 0x0D, "KEY_DELETE": 0x2E, "KEY_PAGEUP": 0x21,
    "KEY_PAGEDOWN": 0x22, "KEY_UP": 0x26, "KEY_DOWN": 0x28, "KEY_LEFT": 0x25,
    "KEY_RIGHT": 0x27, "KEY_MINUS": 0xBD, "KEY_EQUAL": 0xBB, "KEY_LEFTBRACE": 0xDB,
    "KEY_RIGHTBRACE": 0xDD, "KEY_BACKSLASH": 0xDC, "KEY_SEMICOLON": 0xBA,
    "KEY_APOSTROPHE": 0xDE, "KEY_COMMA": 0xBC, "KEY_DOT": 0xBE, "KEY_SLASH": 0xBF,
    **{f"KEY_{c}": ord(c) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"},
}


class KeyListener:
    """Collects pressed keys as Windows VK codes; drain() returns new presses."""

    def __init__(self):
        self._q = queue.Queue()
        if sys.platform.startswith("linux"):
            threading.Thread(target=self._run_evdev, daemon=True).start()
        else:
            self._start_pynput()

    def drain(self):
        out = []
        while not self._q.empty():
            out.append(self._q.get_nowait())
        return out

    def _start_pynput(self):
        from pynput import keyboard

        def on_press(key):
            vk = getattr(key, "vk", None)
            if vk is None and hasattr(key, "value"):
                vk = getattr(key.value, "vk", None)
            if vk is not None:
                self._q.put(vk)

        self._listener = keyboard.Listener(on_press=on_press)
        self._listener.daemon = True
        self._listener.start()

    def _run_evdev(self):
        import selectors

        import evdev
        from evdev import ecodes

        devices = [evdev.InputDevice(p) for p in evdev.list_devices()]
        devices = [d for d in devices if d.info.vendor == 0x258A and d.info.product == 0x010C
                   and ecodes.EV_KEY in d.capabilities()] or \
                  [d for d in devices if ecodes.EV_KEY in d.capabilities()]
        sel = selectors.DefaultSelector()
        for d in devices:
            sel.register(d, selectors.EVENT_READ)
        while True:
            for key, _ in sel.select():
                for ev in key.fileobj.read():
                    if ev.type == ecodes.EV_KEY and ev.value == 1:
                        name = ecodes.KEY.get(ev.code)
                        name = name[0] if isinstance(name, list) else name
                        vk = _EVDEV_TO_VK.get(name)
                        if vk is not None:
                            self._q.put(vk)
