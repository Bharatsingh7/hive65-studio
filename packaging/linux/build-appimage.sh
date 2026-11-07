#!/usr/bin/env bash
# Build Hive65-Studio-x86_64.AppImage on Linux (Arch / Hyprland tested target).
# Usage: bash packaging/linux/build-appimage.sh      -> dist/Hive65-Studio-x86_64.AppImage
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="${XDG_CACHE_HOME:-$HOME/.cache}/hive65-appimage"
VENV="$WORK/venv"
APPDIR="$WORK/AppDir"
OUT="$ROOT/dist"
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT/pyproject.toml")"
mkdir -p "$WORK" "$OUT"

# --- build tools (Arch). Other distros: install the same things with your package manager.
if command -v pacman >/dev/null; then
    PKGS=(python hidapi libusb libpulse base-devel python-gobject gst-plugin-pipewire gst-plugins-base wget)
    if ! pacman -T "${PKGS[@]}" >/dev/null 2>&1; then
        sudo pacman -S --needed --noconfirm "${PKGS[@]}"
    fi
fi

# --- venv: system site-packages so PyGObject (portal screen capture) is bundled too
if [ ! -x "$VENV/bin/python" ]; then
    python -m venv --system-site-packages "$VENV"
fi
if command -v uv >/dev/null; then
    uv pip install --python "$VENV/bin/python" "$ROOT[all]" pyinstaller
else
    "$VENV/bin/pip" install -q --upgrade pip wheel
    "$VENV/bin/pip" install -q "$ROOT[all]" pyinstaller
fi

EXTRA=()
if "$VENV/bin/python" -c "import gi" 2>/dev/null; then
    EXTRA+=(--hidden-import gi --collect-submodules gi)
fi

# --- one folder build: Studio by default, the CLI when given a subcommand
"$VENV/bin/python" -m PyInstaller --noconfirm --clean --onedir --name hive65 \
    --workpath "$WORK/build" --specpath "$WORK" --distpath "$WORK/dist" \
    --paths "$ROOT" --add-data "$ROOT/hive65/data:hive65/data" \
    --collect-submodules hive65 --collect-data qtawesome \
    --hidden-import hidraw --hidden-import evdev --hidden-import soundcard \
    --hidden-import dbus_next --hidden-import mss \
    "${EXTRA[@]}" "$ROOT/packaging/linux/appimage_entry.py"

# --- AppDir
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/256x256/apps" "$APPDIR/usr/lib/udev/rules.d"
cp -a "$WORK/dist/hive65/." "$APPDIR/usr/bin/"
cp "$ROOT/packaging/hive65.png" "$APPDIR/hive65.png"
cp "$ROOT/packaging/hive65.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/hive65.png"
cp "$ROOT/packaging/linux/70-hive65.rules" "$APPDIR/usr/lib/udev/rules.d/"

cat > "$APPDIR/hive65.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Hive65 Studio
Comment=Effects, music lighting and notifications for the Kreo Hive 65
Exec=hive65
Icon=hive65
Categories=Utility;Settings;HardwareSettings;
Keywords=keyboard;rgb;lighting;kreo;
StartupWMClass=hive65
EOF
cp "$APPDIR/hive65.desktop" "$APPDIR/usr/share/applications/"

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
RULE=/etc/udev/rules.d/70-hive65.rules
case "$1" in
  --install-udev)
    # One-time: let your user talk to the keyboard without root.
    if command -v pkexec >/dev/null 2>&1; then
      pkexec sh -c "cp '$HERE/usr/lib/udev/rules.d/70-hive65.rules' '$RULE' && udevadm control --reload && udevadm trigger" || exit 1
    else
      sudo cp "$HERE/usr/lib/udev/rules.d/70-hive65.rules" "$RULE" && sudo udevadm control --reload && sudo udevadm trigger || exit 1
    fi
    echo "udev rule installed successfully."
    exit 0 ;;
  --install-desktop)
    # Add Hive65 Studio to your app launcher (rofi, wofi, fuzzel...).
    APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
    ICONS="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps"
    mkdir -p "$APPS" "$ICONS"
    cp "$HERE/hive65.png" "$ICONS/hive65.png"
    sed "s|^Exec=.*|Exec=\"$APPIMAGE\"|" "$HERE/hive65.desktop" > "$APPS/hive65-studio.desktop"
    echo "Added Hive65 Studio to $APPS"
    if [ ! -e "$RULE" ]; then
      echo "Note: Keyboard access requires a udev rule. Run:"
      echo "  \"$APPIMAGE\" --install-udev"
    fi
    exit 0 ;;
esac
if [ ! -e "$RULE" ] && [ -z "$HIVE65_NO_UDEV_HINT" ]; then
    echo "hive65: keyboard access needs a udev rule once: \"$APPIMAGE\" --install-udev" >&2
fi
exec "$HERE/usr/bin/hive65" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# --- appimagetool
TOOL="$WORK/appimagetool-x86_64.AppImage"
if [ ! -x "$TOOL" ]; then
    if command -v appimagetool >/dev/null; then
        TOOL="$(command -v appimagetool)"
    else
        wget -q -O "$TOOL" \
            https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
        chmod +x "$TOOL"
    fi
fi
TARGET="$OUT/Hive65-Studio-$VERSION-x86_64.AppImage"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream "$APPDIR" "$TARGET"
echo
echo "Built $TARGET"
echo "First run:  \"$TARGET\" --install-udev      (once, asks for your password)"
echo "Launcher:   \"$TARGET\" --install-desktop"
echo "Start:      \"$TARGET\"          CLI:  \"$TARGET\" scene Party"
