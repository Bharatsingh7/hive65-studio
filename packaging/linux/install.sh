#!/bin/sh
# Install hive65 + Hive65 Studio for the current user on Arch / Hyprland.
#   sh packaging/linux/install.sh            install
#   sh packaging/linux/install.sh --uninstall
set -eu
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
VENV="$HOME/.local/share/hive65/venv"
BIN="$HOME/.local/bin"
UNITS="$HOME/.config/systemd/user"
APPS="$HOME/.local/share/applications"

if [ "${1:-}" = "--uninstall" ]; then
    systemctl --user disable --now hive65.service 2>/dev/null || true
    rm -rf "$VENV" "$BIN/hive65" "$BIN/hive65-studio" "$UNITS/hive65.service" \
           "$APPS/hive65-studio.desktop" "$HOME/.config/autostart/hive65-studio.desktop"
    sudo rm -f /etc/udev/rules.d/70-hive65.rules && sudo udevadm control --reload
    echo "hive65 removed."
    exit 0
fi

if command -v pacman >/dev/null; then
    # hidapi: device access; libpulse: audio loopback (PipeWire's pulse server);
    # python-gobject + gst-plugin-pipewire + portal: screen capture on Wayland;
    # grim: capture fallback; wireplumber: volume events; brightnessctl: optional.
    sudo pacman -S --needed --noconfirm python hidapi libpulse base-devel \
        python-gobject gst-plugin-pipewire gst-plugins-base xdg-desktop-portal-hyprland \
        grim wireplumber qt6-wayland
fi

# --system-site-packages lets the venv use the distro's PyGObject (GStreamer).
python -m venv --system-site-packages "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q "$ROOT[all]"
mkdir -p "$BIN" "$UNITS" "$APPS"
ln -sf "$VENV/bin/hive65" "$BIN/hive65"
ln -sf "$VENV/bin/hive65-studio" "$BIN/hive65-studio"

cat > "$APPS/hive65-studio.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Hive65 Studio
Comment=Effects, notifications and remapping for the Kreo Hive 65
Exec=$BIN/hive65-studio
Icon=input-keyboard
Categories=Settings;HardwareSettings;
EOF

# Headless alternative to the GUI (e.g. no tray on your bar): effects + notifications.
cat > "$UNITS/hive65.service" <<EOF
[Unit]
Description=hive65 effects and notifications (headless)
After=graphical-session.target pipewire.service
PartOf=graphical-session.target

[Service]
ExecStart=$BIN/hive65 serve
Restart=on-failure
RestartSec=3

[Install]
WantedBy=graphical-session.target
EOF
systemctl --user daemon-reload

sudo install -m 644 "$ROOT/packaging/linux/70-hive65.rules" /etc/udev/rules.d/
sudo udevadm control --reload
sudo udevadm trigger --attr-match=idVendor=258a

cat <<EOF

Installed.
  hive65-studio                      the app (tray icon needs a StatusNotifier tray, e.g. waybar)
  systemctl --user enable --now hive65.service   headless instead of the app
  hive65 notify volume 0.5          test an animation

Hyprland: volume/brightness keys are picked up automatically (wpctl, /sys/class/backlight).
Optional binds, e.g. to flash on a screenshot:
  bind = , Print, exec, grim && hive65 notify flash -c white
EOF
