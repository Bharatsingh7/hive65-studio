"""Key remapping (base layer and FN layer), stored on the keyboard.

Key map (cmd 0x03, idx 0 = base layer, idx 1 = FN layer): one 32-bit
big-endian action per LED index:
    0x00MM00UU  keyboard: modifier mask MM + HID usage UU
    0x0200UUUU  consumer control (media keys)
    0x07xxxxxx  / 0x08xxxxxx  firmware functions / lighting control (FN layer)
"""
import re

from .device import CMD_KEYMAP, KEYMAP_LEN

BASE, FN = 0, 1
PROTECTED = {"fn"}  # never remap: losing FN would lock you out of the FN layer

MODIFIERS = {"lctrl": 0x01, "ctrl": 0x01, "lshift": 0x02, "shift": 0x02, "lalt": 0x04,
             "alt": 0x04, "lwin": 0x08, "win": 0x08, "super": 0x08, "rctrl": 0x10,
             "rshift": 0x20, "ralt": 0x40, "rwin": 0x80}

USAGES = {
    **{c: 0x04 + i for i, c in enumerate("abcdefghijklmnopqrstuvwxyz")},
    **{str(n): 0x1E + (n - 1) for n in range(1, 10)}, "0": 0x27,
    "enter": 0x28, "esc": 0x29, "backspace": 0x2A, "tab": 0x2B, "space": 0x2C,
    "-": 0x2D, "=": 0x2E, "[": 0x2F, "]": 0x30, "\\": 0x31, ";": 0x33, "'": 0x34,
    "`": 0x35, ",": 0x36, ".": 0x37, "/": 0x38, "capslock": 0x39,
    **{f"f{n}": 0x3A + n - 1 for n in range(1, 13)},
    "printscreen": 0x46, "scrolllock": 0x47, "pause": 0x48, "insert": 0x49,
    "home": 0x4A, "pgup": 0x4B, "delete": 0x4C, "end": 0x4D, "pgdn": 0x4E,
    "right": 0x4F, "left": 0x50, "down": 0x51, "up": 0x52, "menu": 0x65,
    "none": 0x00,
}
CONSUMER = {"mute": 0xE2, "volup": 0xE9, "voldown": 0xEA, "play": 0xCD, "next": 0xB5,
            "prev": 0xB6, "stop": 0xB7, "calc": 0x192, "mail": 0x18A, "browser": 0x196}

_REV_USAGE = {v: k for k, v in USAGES.items()}
_REV_MOD = {0x01: "lctrl", 0x02: "lshift", 0x04: "lalt", 0x08: "lwin", 0x10: "rctrl",
            0x20: "rshift", 0x40: "ralt", 0x80: "rwin"}
_REV_CONSUMER = {v: k for k, v in CONSUMER.items()}


def encode(action):
    """'esc', 'ctrl+c', 'mute', 'lshift', or a raw '0x...' value -> 32-bit action."""
    a = action.strip().lower()
    if re.fullmatch(r"0x[0-9a-f]{1,8}", a):
        return int(a, 16)
    if a in CONSUMER:
        return 0x02000000 | CONSUMER[a]
    mods, usage = 0, 0
    for part in a.split("+"):
        if part in MODIFIERS:
            mods |= MODIFIERS[part]
        elif part in USAGES:
            usage = USAGES[part]
        else:
            raise ValueError(f"unknown key '{part}'")
    return (mods << 16) | usage


def describe(value):
    kind = value >> 24
    if kind == 0x00:
        mods, usage = (value >> 16) & 0xFF, value & 0xFF
        parts = [n for bit, n in _REV_MOD.items() if mods & bit]
        if usage:
            parts.append(_REV_USAGE.get(usage, f"usage_0x{usage:02x}"))
        return "+".join(parts) or "none"
    if kind == 0x02:
        u = value & 0xFFFF
        return _REV_CONSUMER.get(u, f"consumer_0x{u:04x}")
    return f"0x{value:08x}"


class Keymap:
    def __init__(self, kb, layout):
        self.kb, self.layout = kb, layout

    def read(self, layer=BASE):
        raw = self.kb.read(CMD_KEYMAP, KEYMAP_LEN, idx=layer)
        return bytearray(raw)

    def get(self, layer=BASE):
        raw = self.read(layer)
        return {k.name: int.from_bytes(raw[k.led * 4: k.led * 4 + 4], "big")
                for k in self.layout.keys}

    def write_raw(self, raw, layer=BASE):
        raw = bytes(raw)
        if raw[-2:] != b"\x5a\xa5":
            raise ValueError("key map block is missing its 5a a5 trailer")
        self.kb.write(CMD_KEYMAP, raw, idx=layer)

    def remap(self, changes, layer=BASE):
        """changes: {key name: action string or int}."""
        raw = self.read(layer)
        for name, action in changes.items():
            key = self.layout.key(name)
            if key.name.lower() in PROTECTED:
                raise ValueError(f"refusing to remap {key.name}")
            value = action if isinstance(action, int) else encode(action)
            raw[key.led * 4: key.led * 4 + 4] = value.to_bytes(4, "big")
        self.write_raw(raw, layer)
