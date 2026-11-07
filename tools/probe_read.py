"""Read-only probe: GET_FEATURE on the vendor collections of the Kreo Hive 65."""
import hid

VID, PID = 0x258A, 0x010C


def open_col(col):
    for d in hid.enumerate(VID, PID):
        if f"&Col{col:02d}".lower() in d["path"].decode().lower():
            h = hid.device()
            h.open_path(d["path"])
            return h
    raise SystemExit(f"Col{col:02d} not found")


for col, rid, size in ((5, 5, 6), (6, 6, 520)):
    h = open_col(col)
    try:
        data = bytes(h.get_feature_report(rid, size))
        print(f"Col{col:02d} report {rid}: {len(data)} bytes")
        for off in range(0, min(len(data), 128), 32):
            print(f"  {off:04x}: {data[off:off + 32].hex(' ')}")
    except OSError as e:
        print(f"Col{col:02d} report {rid}: error {e}")
    finally:
        h.close()
