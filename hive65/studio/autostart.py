"""Start Hive65 Studio at login (Windows Startup folder / XDG autostart)."""
import os
import sys
from pathlib import Path


def _command():
    if os.environ.get("APPIMAGE"):             # the .AppImage file, not its temporary mount
        return [os.environ["APPIMAGE"], "--minimized"]
    if getattr(sys, "frozen", False):          # PyInstaller exe
        return [sys.executable, "--minimized"]
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe") if sys.platform == "win32" else exe
    return [str(pyw if pyw.exists() else exe), "-m", "hive65.studio.app", "--minimized"]


def _windows_link():
    return Path(os.environ["APPDATA"]) / r"Microsoft\Windows\Start Menu\Programs\Startup\Hive65 Studio.lnk"


def _linux_desktop():
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "autostart" / "hive65-studio.desktop"


def is_enabled():
    return (_windows_link() if sys.platform == "win32" else _linux_desktop()).exists()


def set_enabled(on):
    cmd = _command()
    if sys.platform == "win32":
        link = _windows_link()
        if not on:
            link.unlink(missing_ok=True)
            return
        import subprocess
        args = " ".join(f'"{a}"' if " " in a else a for a in cmd[1:])
        ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{link}');"
              f"$s.TargetPath='{cmd[0]}';$s.Arguments='{args}';$s.Save()")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False,
                       creationflags=0x08000000)
    else:
        f = _linux_desktop()
        if not on:
            f.unlink(missing_ok=True)
            return
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("[Desktop Entry]\nType=Application\nName=Hive65 Studio\n"
                     f"Exec={' '.join(cmd)}\nX-GNOME-Autostart-enabled=true\n")
