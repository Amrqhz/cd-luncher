#!/usr/bin/env bash
# Install:    ./install.sh
# Uninstall:  ./install.sh uninstall
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/bin/cd-launcher"
APPS="$HOME/.local/share/applications"
AUTOSTART="$HOME/.config/autostart"
DESKTOP="$APPS/io.github.amrqhz.cd.desktop"
AUTO_DESKTOP="$AUTOSTART/io.github.amrqhz.cd-autostart.desktop"

if [ "$1" = "uninstall" ]; then
    "$BIN" --quit 2>/dev/null || true
    "$BIN" --remove-shortcut 2>/dev/null || true
    rm -f "$BIN" "$DESKTOP" "$AUTO_DESKTOP"
    echo "cd removed. (Your settings in ~/.config/cd-launcher were kept.)"
    exit 0
fi

if ! python3 -c "import gi; gi.require_version('Gtk','4.0'); gi.require_version('Adw','1'); from gi.repository import Adw; Adw.SwitchRow" 2>/dev/null; then
    echo "Missing dependencies (need libadwaita >= 1.4). Install with:"
    echo "  Fedora:  sudo dnf install python3-gobject gtk4 libadwaita poppler-glib python3-cairo"
    echo "  Ubuntu:  sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-poppler-0.18 python3-gi-cairo"
    echo "  Arch:    sudo pacman -S python-gobject gtk4 libadwaita poppler-glib python-cairo"
    exit 1
fi

# stop an older running copy so the new code is used
[ -x "$BIN" ] && "$BIN" --quit 2>/dev/null || true

install -Dm755 "$DIR/cd.py" "$BIN"
mkdir -p "$APPS" "$AUTOSTART"

cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=cd
Comment=Jump to any folder or file by typing its path
Exec=$BIN
Icon=folder-open-symbolic
Terminal=false
Categories=Utility;System;
Actions=Settings;

[Desktop Action Settings]
Name=Settings
Exec=$BIN --settings
EOF

cat > "$AUTO_DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=cd (background)
Exec=$BIN --background
X-GNOME-Autostart-enabled=true
NoDisplay=true
EOF

"$BIN" --apply-shortcut
nohup "$BIN" --background >/dev/null 2>&1 &

echo "Done. Press the shortcut above to open cd, or change it in cd's settings."
