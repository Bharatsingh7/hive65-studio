# Kreo Hive 65 USB protocol

Reverse engineered from USB captures of the vendor app (`OemDrv.exe` v2.0,
2025-03-05). Each item is marked **verified** (we sent it from our own code
and saw the right result on the keyboard) or **observed** (seen in a capture
but not yet sent by us).

## Device

| | |
|---|---|
| USB ID | `258a:010c` (SinoWealth), full-speed composite |
| MI_00 | boot keyboard |
| MI_01 | Col01 system control, Col02 consumer, Col03 vendor in (4 B), Col04 NKRO keyboard, **Col05 feature report 5 (6 B)**, **Col06 feature report 6 (520 B)**, Col07 mouse |
| Config channel | **feature report 6, 520 bytes, on MI_01**. On Windows that is Col06. On Linux it is the MI_01 hidraw node. |

Report 5 was never used by the app, and reading it returns an error.

## Message format

All traffic is `SET_FEATURE` / `GET_FEATURE` on report 6, zero-padded to 520 bytes:

```
off  size  field
0    1     0x06  report id
1    1     cmd   (bit 7 set = read)
2    2     index (LE): 0 normally, 1 = FN layer for the key map, 1 for the info read
4    2     0x0001
6    2     payload length (LE)
8    n     payload
```

**Read:** `SET_FEATURE` the 8-byte header with `cmd | 0x80`, then
`GET_FEATURE`. The reply echoes the header, followed by the payload. Right after
a flash write the keyboard can return all zeros for about 100 ms, so retry.

**Write:** `SET_FEATURE` the header with the payload. Every stored block ends in
the magic bytes `5a a5`, at the position the read returns them; write blocks
back with that position unchanged. There is no CRC.

## Commands

| cmd | len | dir | meaning | status |
|---|---|---|---|---|
| `0x02` | 6 | read (idx 1) | device signature `03 00 00 00 03 09` (`Psd=` in KB.ini) | verified |
| `0x03` | 0x200 | r/w | key map, idx 0 = base layer, idx 1 = FN layer | verified |
| `0x04` | 0x80 | r/w | lighting config | verified |
| `0x06` | 0x17A | r/w | Self-define per-key colours | verified |
| `0x08` | 0x17A | write | **live frame** (RAM only, not saved) | verified |
| `0x0A` | 0x200 | r/w | per-mode colour palette | verified |

`hive65.device` refuses every other opcode, so it can never reach a bootloader
or firmware-update command by accident.

## LED indices

There are 126 slots, column-major with 6 per column: `index = column * 6 + row`.
Only 67 slots have LEDs; KB.ini gives each key's index in the last field of
its `[KEY]` line, e.g. Esc = 1, Tab = 2, Caps = 3, LShift = 4, LCtrl = 5, `1` = 7.
`hive65/data/layout.json` has all of them.

## Live frame (`0x08`)

The payload is 126 × interleaved `R G B`, so LED *i* is at bytes `3i..3i+2`.
The keyboard shows the frame at once. When frames stop arriving, it goes back
to its stored mode. The vendor app streams at about 21 fps; we use 30 fps
without errors.

## Lighting config (`0x04`, 128 bytes)

| offset | meaning |
|---|---|
| 9 | 1 if mode is Self-define, else 0 |
| 10 | mode id |
| 58 + 2(m−1) | brightness 0–4 for mode *m* |
| 59 + 2(m−1) | `(speed << 4) \| colour`; speed 0 = slowest … 4 = fastest; colour 0–6 = palette slot, 7 = multicolour |
| 126–127 | `5a a5` |

The rest is preserved as read; it holds debounce, sleep, report rate and similar settings, not yet mapped.

Mode ids, from `LedOpt` in KB.ini and `tc_kb_led*` in text.xml:

1 fixed_on, 2 respire, 3 rainbow, 4 flash_away, 5 raindrops, 6 rainbow_wheel,
7 ripples_shining, 8 stars_twinkle, 9 shadow_disappear, 10 retro_snake,
11 neon_stream, 12 reaction, 13 sine_wave, 14 retinue_scanning,
15 rotating_windmill, 16 colorful_waterfall, 17 blossoming, 18 rotating_storm,
21 self_define, 0 off.

**Save sequence** (this is what the vendor app does, and the firmware only
reloads the effect parameters after it):
1. write the palette (`0x0A`)
2. read the config (`0x84`)
3. write the config (`0x04`)

## Palette (`0x0A`, 512 bytes)

There are 7 RGB slots per mode at offset `21 × mode`. The defaults are red,
green, blue, yellow, magenta, cyan, white. When you pick a single colour, the
app writes it to slot 0 and sets the colour nibble to 0. The magic `5a a5` is
at offset 506.

## Self-define colours (`0x06`, 378 bytes)

The layout is planar: `R[126]`, then `G[126]`, then `B[126]`, indexed by LED.
After writing, select mode 21 (Self-define).

## Key map (`0x03`, 512 bytes)

There is one 32-bit **big-endian** action per LED index, at `4 × index`:

| value | action |
|---|---|
| `0x00MM00UU` | keyboard: modifier mask MM (1 LCtrl, 2 LShift, 4 LAlt, 8 LGUI, 0x10–0x80 right side) + HID usage UU |
| `0x0200UUUU` | consumer control (e.g. `0xE2` mute, `0xCD` play/pause) |
| `0x07xxxxxx` | firmware function (FN layer: Win lock, etc.) |
| `0x08xxxxxx` | lighting control (FN layer: mode, brightness, speed) |

The block ends in `5a a5`. The FN key's own slot (LED 59) is never remapped
by hive65.

## Not covered

- **Macros:** left out on purpose.
- **Report rate, debounce and sleep:** these live in config bytes that hive65
  keeps as read but doesn't decode yet.
- **Firmware update:** never touched.
