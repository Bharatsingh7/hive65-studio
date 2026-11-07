"""Low-level HID transport for the Kreo Hive 65 (SinoWealth 258a:010c).

All configuration goes through 520-byte feature report 6 on the vendor
collection (usage page 0xFF00, Col06 on Windows / the 520-byte report on Linux):

    06 | cmd | idx_lo idx_hi | 01 00 | len_lo len_hi | payload ...

Reads are the write command with bit 7 set: SET_FEATURE the header, then
GET_FEATURE returns header + payload. Written config blocks end in 5a a5.
"""
import os
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

if sys.platform.startswith("linux"):
    # The libusb backend of `hid` would detach the kernel driver and the
    # keyboard would stop typing; hidraw talks alongside it.
    import hidraw as hid
else:
    import hid

VID, PID = 0x258A, 0x010C
REPORT_ID = 0x06
REPORT_LEN = 520
DEVICE_SIGNATURE = bytes([0x03, 0x00, 0x00, 0x00, 0x03, 0x09])  # KB.ini Psd=

CMD_INFO = 0x02      # 6 bytes, read-only
CMD_KEYMAP = 0x03    # 512 bytes: 4-byte action per LED index
CMD_CONFIG = 0x04    # 128-byte lighting/settings block
CMD_CUSTOM = 0x06    # 378 bytes: saved "Self-define" colours, planar R[126] G[126] B[126]
CMD_FRAME = 0x08     # live per-key RGB frame, interleaved RGB x 126, RAM only
CMD_PALETTE = 0x0A   # 512-byte per-mode colour table
READ = 0x80

KEYMAP_LEN = 0x200
CONFIG_LEN = 0x80
CUSTOM_LEN = 0x17A
PALETTE_LEN = 0x200

# Commands we have seen the official app send. Anything else is refused so a
# typo can never hit a bootloader/ISP opcode.
KNOWN_WRITES = {CMD_KEYMAP, CMD_CONFIG, CMD_CUSTOM, CMD_FRAME, CMD_PALETTE}
KNOWN_READS = {CMD_INFO, CMD_KEYMAP, CMD_CONFIG, CMD_CUSTOM, CMD_PALETTE}
BLOCK_MAGIC = b"\x5a\xa5"


class DeviceError(RuntimeError):
    pass


# Reads share one reply buffer with live frames, so a config session asks any
# running effect (another process) to hold its frames while this file exists.
PAUSE_FILE = Path(tempfile.gettempdir()) / "hive65.pause"
PAUSE_STALE = 60  # seconds; ignore a pause file left by a crashed process


@contextmanager
def pause_streams():
    PAUSE_FILE.write_text(str(os.getpid()))
    time.sleep(0.1)  # let a streaming effect notice and finish its frame
    try:
        yield
    finally:
        PAUSE_FILE.unlink(missing_ok=True)


def streams_paused():
    try:
        return time.time() - PAUSE_FILE.stat().st_mtime < PAUSE_STALE
    except OSError:
        return False


def _find_config_path():
    # Windows lists one entry per collection (usage page 0xFF00 = vendor);
    # Linux hidraw lists one node per interface, and the config one is MI_01.
    candidates = [d["path"] for d in hid.enumerate(VID, PID) if d["usage_page"] == 0xFF00]
    candidates += [d["path"] for d in hid.enumerate(VID, PID)
                   if d["interface_number"] == 1 and d["path"] not in candidates]
    perm_denied = False
    for path in candidates:
        h = hid.device()
        try:
            h.open_path(path)
            # The config collection is the only one that answers feature report 6.
            h.get_feature_report(REPORT_ID, REPORT_LEN)
            return path
        except (OSError, ValueError):
            if sys.platform.startswith("linux"):
                path_str = path.decode("utf-8", "ignore") if isinstance(path, bytes) else str(path)
                if os.path.exists(path_str) and not os.access(path_str, os.R_OK | os.W_OK):
                    perm_denied = True
            continue
        finally:
            h.close()
    if perm_denied:
        raise DeviceError("Kreo Hive 65 keyboard detected, but permission was denied accessing it.\n"
                          "Install the udev rule once: Hive65.AppImage --install-udev")
    raise DeviceError("Kreo Hive 65 (258a:010c) config interface not found. "
                      "Is it plugged in, and is the Kreo app closed?")


class Hive65:
    def __init__(self, path=None):
        self._h = hid.device()
        self._h.open_path(path or _find_config_path())

    def close(self):
        self._h.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @staticmethod
    def _header(cmd, length, idx=0):
        return bytes([REPORT_ID, cmd, idx & 0xFF, idx >> 8, 0x01, 0x00,
                      length & 0xFF, length >> 8])

    def _send(self, buf):
        buf = buf.ljust(REPORT_LEN, b"\x00")
        if self._h.send_feature_report(buf) < 0:
            raise DeviceError(f"SET_FEATURE failed: {self._h.error()}")

    def read(self, cmd, length, idx=0):
        if cmd not in KNOWN_READS:
            raise DeviceError(f"refusing unknown read command 0x{cmd:02x}")
        for attempt in range(5):
            self._send(self._header(cmd | READ, length, idx))
            time.sleep(0.02 + 0.05 * attempt)
            resp = bytes(self._h.get_feature_report(REPORT_ID, REPORT_LEN)).ljust(REPORT_LEN, b"\0")
            if resp[1] == cmd | READ:
                return resp[8:8 + length]
        raise DeviceError(f"unexpected reply {resp[:8].hex(' ')}")

    def write(self, cmd, payload, idx=0):
        if cmd not in KNOWN_WRITES:
            raise DeviceError(f"refusing unknown write command 0x{cmd:02x}")
        self._send(self._header(cmd, len(payload), idx) + bytes(payload))
        if cmd != CMD_FRAME:
            time.sleep(0.1)  # the firmware is busy saving to flash

    def info(self):
        return self.read(CMD_INFO, 6, idx=1)

    def check_signature(self):
        sig = self.info()
        if sig != DEVICE_SIGNATURE:
            raise DeviceError(f"unexpected device signature {sig.hex(' ')}")
        return sig
