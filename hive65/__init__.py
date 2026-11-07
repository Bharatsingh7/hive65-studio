"""Open-source driver for the Kreo Hive 65 keyboard (Linux and Windows)."""
from .device import Hive65, DeviceError

__all__ = ["Hive65", "DeviceError"]
