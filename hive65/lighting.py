"""Hardware lighting modes stored on the keyboard (survive unplugging).

Config block (cmd 0x04, 128 bytes):
    [9]          1 when mode is Self-define, else 0
    [10]         mode id (see MODES)
    [58 + 2(m-1)] brightness 0..4 for mode m
    [59 + 2(m-1)] (speed << 4) | colour slot (0..6 = palette slot, 7 = multicolour)
Palette (cmd 0x0A, 512 bytes): 7 RGB slots per mode at offset 21 * m.
Self-define colours (cmd 0x06): planar R[126] G[126] B[126].
"""
from dataclasses import dataclass

from .device import (CMD_CONFIG, CMD_CUSTOM, CMD_PALETTE, CONFIG_LEN, CUSTOM_LEN,
                     PALETTE_LEN)
from .layout import NUM_LEDS

OFF, SELF_DEFINE = 0, 21
CFG_CUSTOM_FLAG, CFG_MODE, CFG_PARAMS = 9, 10, 58
MULTICOLOR = 7


@dataclass(frozen=True)
class Mode:
    id: int
    name: str
    speed: bool
    color: bool  # supports a single colour / multicolour choice


# From KB.ini LedOpt1..20 (id, speed, colour) and text.xml tc_kb_led names.
MODES = [Mode(*m) for m in [
    (1, "fixed_on", False, True), (2, "respire", True, True), (3, "rainbow", True, False),
    (4, "flash_away", True, True), (5, "raindrops", True, True),
    (6, "rainbow_wheel", True, True), (7, "ripples_shining", True, True),
    (8, "stars_twinkle", True, True), (9, "shadow_disappear", True, True),
    (10, "retro_snake", True, True), (11, "neon_stream", True, True),
    (12, "reaction", True, True), (13, "sine_wave", True, True),
    (14, "retinue_scanning", True, True), (15, "rotating_windmill", True, False),
    (16, "colorful_waterfall", True, False), (17, "blossoming", True, False),
    (18, "rotating_storm", True, True), (SELF_DEFINE, "self_define", False, False),
    (OFF, "off", False, False),
]]
MODES_BY_NAME = {m.name: m for m in MODES}
MODES_BY_ID = {m.id: m for m in MODES}


def find_mode(name_or_id):
    if str(name_or_id).isdigit():
        return MODES_BY_ID[int(name_or_id)]
    return MODES_BY_NAME[str(name_or_id).lower().replace("-", "_").replace(" ", "_")]


class Lighting:
    def __init__(self, kb):
        self.kb = kb

    def state(self):
        cfg = self.kb.read(CMD_CONFIG, CONFIG_LEN)
        mode = MODES_BY_ID.get(cfg[CFG_MODE], Mode(cfg[CFG_MODE], "unknown", False, False))
        out = {"mode": mode.name, "mode_id": mode.id}
        if 1 <= mode.id <= 32:
            b, p = cfg[CFG_PARAMS + 2 * (mode.id - 1): CFG_PARAMS + 2 * mode.id]
            out.update(brightness=b, speed=p >> 4, color_slot=p & 0x0F)
        return out

    def apply(self, mode=None, brightness=None, speed=None, color=None, multicolor=False):
        """Change the stored mode and/or its settings, like the app's Save button.

        color: (r, g, b) bytes, stored in palette slot 0 of that mode.
        """
        cfg = bytearray(self.kb.read(CMD_CONFIG, CONFIG_LEN))
        m = find_mode(mode) if mode is not None else MODES_BY_ID.get(cfg[CFG_MODE])
        if m is None:
            raise ValueError(f"current mode {cfg[CFG_MODE]} is unknown; pass a mode")
        if color is not None and not m.color:
            raise ValueError(f"mode {m.name} does not take a colour")
        # Same order as the vendor app's Save: palette, re-read config, config.
        # The firmware only reloads the effect parameters after a palette write.
        pal = bytearray(self.kb.read(CMD_PALETTE, PALETTE_LEN))
        if color is not None:
            pal[21 * m.id: 21 * m.id + 3] = bytes(color)  # 5a a5 at 506 is kept as read
        self.kb.write(CMD_PALETTE, pal)
        cfg = bytearray(self.kb.read(CMD_CONFIG, CONFIG_LEN))
        cfg[CFG_MODE] = m.id
        cfg[CFG_CUSTOM_FLAG] = 1 if m.id == SELF_DEFINE else 0
        if 1 <= m.id <= 32:
            i = CFG_PARAMS + 2 * (m.id - 1)
            if brightness is not None:
                cfg[i] = max(0, min(4, int(brightness)))
            p = cfg[i + 1]
            if speed is not None:
                p = (max(0, min(4, int(speed))) << 4) | (p & 0x0F)
            if color is not None:
                p = (p & 0xF0) | 0
            if multicolor:
                p = (p & 0xF0) | MULTICOLOR
            cfg[i + 1] = p
        self.kb.write(CMD_CONFIG, cfg)

    def set_custom(self, colors):
        """Store per-key colours for Self-define mode. colors: {led_index: (r, g, b)}."""
        planes = bytearray(CUSTOM_LEN)
        for led, (r, g, b) in colors.items():
            planes[led], planes[NUM_LEDS + led], planes[2 * NUM_LEDS + led] = r, g, b
        self.kb.write(CMD_CUSTOM, planes)
        self.apply(mode="self_define")

    def get_custom(self):
        p = self.kb.read(CMD_CUSTOM, CUSTOM_LEN)
        return {i: (p[i], p[NUM_LEDS + i], p[2 * NUM_LEDS + i]) for i in range(NUM_LEDS)
                if p[i] or p[NUM_LEDS + i] or p[2 * NUM_LEDS + i]}
