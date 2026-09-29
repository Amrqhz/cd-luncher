# cd

A small launcher for GNOME. Hit a shortcut, type part of a path, press Enter, and the folder opens in your file manager. Files work too.

I wanted something faster than opening Files and clicking through five folders to reach directories.Add `cd` option from you terminal to the file/app/directory launcher.

    Ctrl+Alt+O  →  downloads/tele  →  Enter

## How it works

Paths are relative to your home folder (you can change that). Matching ignores case, so `downloads/telegram` finds `Downloads/Telegram`. Suggestions pop up under the input as you type, and if the highlighted thing is an image or a PDF you get a preview next to the list.

It's a plain GTK4 / libadwaita app written in Python, one file. There's no Shell extension involved, so GNOME updates shouldn't break it.

The app stays running in the background after login. The shortcut just wakes it up, which is why it opens instantly instead of waiting on Python to start.

## Requirements

- GNOME with libadwaita 1.4 or newer (Fedora 40+, Ubuntu 24.04+, or anything similar)
- Python 3, PyGObject, GTK4, libadwaita
- Poppler (only needed for PDF previews)

Fedora:

    sudo dnf install python3-gobject gtk4 libadwaita poppler-glib python3-cairo

Ubuntu / Debian:

    sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-poppler-0.18 python3-gi-cairo

Arch:

    sudo pacman -S python-gobject gtk4 libadwaita poppler-glib python-cairo

## Install

    chmod +x install.sh
    ./install.sh

This copies `cd.py` to `~/.local/bin/cd-launcher`, adds a desktop entry, sets it to start hidden at login, and registers the default shortcut, **Ctrl+Alt+O**. If the shortcut does nothing right after install, log out and back in once.

To remove it:

    ./install.sh uninstall

Your settings in `~/.config/cd-launcher/` are left alone.

## Keys

| Key | What it does |
| --- | --- |
| Up / Down | move through suggestions |
| Tab | complete the highlighted name |
| Enter | open the folder, or open the file |
| Ctrl+Enter | on a file, do the opposite of Enter (open vs. show in folder) |
| Ctrl+, | settings |
| Esc | hide |

## Settings

Click the gear in the window, or run `cd-launcher --settings`. Everything applies right away.

- **Shortcut.** Click the button and press the combo you want. It needs Ctrl, Alt or Super in it. This writes a normal custom shortcut into GNOME's keyboard settings, so you'll also see it under Settings → Keyboard. `Super+Space` is usually already taken by input switching, so pick something else.
- **Search.** Start folder, show files, show hidden files, folders first, match anywhere in the name, max number of suggestions.
- **Opening.** What Enter does on a file, and an optional file manager command (empty means your system default).
- **Look.** Preview on/off, close on focus loss, animation style and speed, window width, light/dark.

The config is just JSON at `~/.config/cd-launcher/config.json` if you'd rather edit it by hand.

## Command line

    cd-launcher               show the launcher
    cd-launcher --settings    open settings
    cd-launcher --background  start hidden (this is what autostart runs)
    cd-launcher --quit        stop the background copy

After editing `cd.py`, run `./install.sh` again. It restarts the background copy for you.

## Known limits

- Under Wayland an app can't choose where its window appears, so cd opens wherever GNOME puts it, usually centered.
- Only the first page of a PDF is previewed.
- The shortcut setup is GNOME-specific. On other desktops, bind `cd-launcher` to a key yourself.


made by [amrqhz](amrqhz.github,io)
project repo:[cd-luncher](https://github.com/Amrqhz/cd-luncher) 

