"""Dump HID SET/GET_REPORT traffic from USBPcap captures and decode LED frames.

usage: python tools/pcapdump.py <pcap> [--frames N] [--keys KB.ini]
"""
import argparse
import re
import subprocess
from pathlib import Path

TSHARK = r"C:\Program Files\Wireshark\tshark.exe"
KB_INI = r"C:\Program Files (x86)\Kreo Hive 65\Dev\kb\KB.ini"


def load_keys(path):
    """Return {led_index: key_name} from the [KEY] section of KB.ini."""
    keys, name, section = {}, None, None
    for line in Path(path).read_text(encoding="latin-1").splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line
        elif section == "[KEY]" and line.startswith(";"):
            name = line[1:]
        elif section == "[KEY]" and re.match(r"K\d+=", line):
            led = int(line.split(",")[-1])
            keys[led] = name
    return keys


def transfers(pcap):
    out = subprocess.run(
        [TSHARK, "-r", pcap, "-T", "fields", "-E", "separator=|",
         "-e", "frame.time_relative", "-e", "usb.function", "-e", "usb.bmRequestType",
         "-e", "usb.setup.bRequest", "-e", "usb.setup.wValue", "-e", "usb.setup.wIndex",
         "-e", "usb.data_fragment", "-e", "usb.capdata", "-e", "usb.irp_info.direction"],
        capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        t, fn, rt, req, wv, wi, frag, cap, d = line.split("|")
        yield float(t), fn, rt, req, wv, wi, bytes.fromhex(frag or cap or "")


def decode_led_frame(data, keys):
    hdr, rgb = data[:8], data[8:]
    lit = []
    for idx, name in sorted(keys.items()):
        r, g, b = rgb[idx * 3: idx * 3 + 3]
        if r or g or b:
            lit.append(f"{name}=#{r:02x}{g:02x}{b:02x}")
    return hdr.hex(" "), lit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pcap")
    ap.add_argument("--frames", type=int, default=3)
    ap.add_argument("--keys", default=KB_INI)
    a = ap.parse_args()
    keys = load_keys(a.keys)
    shown = 0
    for t, fn, rt, req, wv, wi, data in transfers(a.pcap):
        if not rt:
            continue
        print(f"{t:9.3f} fn={fn} rt={rt} req={req} wValue={wv} wIndex={wi} len={len(data)}")
        if data[:2] == b"\x06\x08" and shown < a.frames:
            hdr, lit = decode_led_frame(data, keys)
            print("   hdr:", hdr)
            print("   lit:", " ".join(lit))
            shown += 1
        elif data and not data[:2] == b"\x06\x08":
            print("   data:", data[:64].hex(" "))


if __name__ == "__main__":
    main()
