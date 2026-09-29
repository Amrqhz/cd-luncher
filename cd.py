#!/usr/bin/env python3
"""cd - type a path, press Enter, it opens. Folders AND files, with preview.

Usage:
  cd-launcher               show the launcher
  cd-launcher --settings    open settings
  cd-launcher --background  start hidden (autostart) so the shortcut is instant
  cd-launcher --quit        stop the background instance
  cd-launcher --apply-shortcut / --remove-shortcut
"""
import json
import os
import shlex
import shutil
import subprocess
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

try:
    gi.require_version("Poppler", "0.18")
    from gi.repository import Poppler
    HAVE_POPPLER = True
except (ValueError, ImportError):
    HAVE_POPPLER = False

APP_ID = "io.github.amrqhz.cd"
HOME = os.path.expanduser("~")
CONFIG_DIR = os.path.join(GLib.get_user_config_dir(), "cd-launcher")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".tiff"}

DEFAULTS = {
    "shortcut": "<Control><Alt>o",
    "start_dir": "~",
    "show_files": True,
    "show_hidden": False,
    "folders_first": True,
    "match_anywhere": True,
    "max_results": 30,
    "enter_on_file": "open",        # open | reveal
    "file_manager": "",             # empty = system default
    "preview": True,
    "close_on_focus_loss": True,
    "width": 720,
    "animation": "slide",           # slide | fade | swing
    "animation_ms": 220,
    "theme": "system",              # system | light | dark | gruvbox-dark | catppuccin-mocha | ...
}


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------
class Config:
    def __init__(self):
        self.data = dict(DEFAULTS)
        try:
            with open(CONFIG_FILE) as f:
                saved = json.load(f)
            self.data.update({k: v for k, v in saved.items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass

    def __getitem__(self, key):
        return self.data[key]

    def set(self, key, value):
        self.data[key] = value
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.data, f, indent=2)


cfg = Config()


# --------------------------------------------------------------------------
# GNOME keyboard shortcut (custom keybinding via gsettings)
# --------------------------------------------------------------------------
KB_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
KB_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/cd-launcher/"
KB_ITEM = KB_SCHEMA + ".custom-keybinding"


def launcher_command():
    return shutil.which("cd-launcher") or "python3 " + shlex.quote(os.path.abspath(sys.argv[0]))


def apply_shortcut(accel):
    s = Gio.Settings.new(KB_SCHEMA)
    paths = list(s.get_strv("custom-keybindings"))
    if KB_PATH not in paths:
        paths.append(KB_PATH)
        s.set_strv("custom-keybindings", paths)
    item = Gio.Settings.new_with_path(KB_ITEM, KB_PATH)
    item.set_string("name", "cd")
    item.set_string("command", launcher_command())
    item.set_string("binding", accel)
    Gio.Settings.sync()


def remove_shortcut():
    s = Gio.Settings.new(KB_SCHEMA)
    s.set_strv("custom-keybindings", [p for p in s.get_strv("custom-keybindings") if p != KB_PATH])
    item = Gio.Settings.new_with_path(KB_ITEM, KB_PATH)
    for key in ("name", "command", "binding"):
        item.reset(key)
    Gio.Settings.sync()


def accel_label(accel):
    parsed = Gtk.accelerator_parse(accel)
    ok, key, mods = parsed if len(parsed) == 3 else (True, *parsed)
    return Gtk.accelerator_get_label(key, mods) if ok and key else "Not set"


# --------------------------------------------------------------------------
# path logic
# --------------------------------------------------------------------------
def base_dir():
    return os.path.expanduser(cfg["start_dir"] or "~")


def resolve_dir(path):
    """Resolve a path case-insensitively, one component at a time."""
    cur = "/"
    for part in [p for p in path.split("/") if p]:
        nxt = os.path.join(cur, part)
        if not os.path.exists(nxt):
            try:
                match = next((n for n in os.listdir(cur) if n.lower() == part.lower()), None)
            except OSError:
                return None
            if match is None:
                return None
            nxt = os.path.join(cur, match)
        cur = nxt
    return os.path.normpath(cur)


def absolute(text):
    text = text.strip()
    if text in ("~", "."):
        text += "/"
    text = os.path.expanduser(text)
    if not text.startswith("/"):
        text = os.path.join(base_dir(), text)
    return text


def split_query(text):
    full = absolute(text)
    if full.endswith("/"):
        return resolve_dir(full), ""
    return resolve_dir(os.path.dirname(full)), os.path.basename(full)


def list_matches(text):
    folder, prefix = split_query(text)
    if not folder:
        return []
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return []
    p = prefix.lower()
    show_hidden = cfg["show_hidden"] or prefix.startswith(".")
    scored = []
    for e in entries:
        name = e.name
        if name.startswith(".") and not show_hidden:
            continue
        try:
            is_dir = e.is_dir()
        except OSError:
            is_dir = False
        if not is_dir and not cfg["show_files"]:
            continue
        low = name.lower()
        if not p or low.startswith(p):
            rank = 0
        elif cfg["match_anywhere"] and p in low:
            rank = 1
        else:
            continue
        scored.append((rank, (not is_dir) if cfg["folders_first"] else False, low, e.path, is_dir))
    scored.sort()
    return [(path, is_dir) for _r, _f, _n, path, is_dir in scored[: int(cfg["max_results"])]]


def shorten(path):
    base = base_dir().rstrip("/")
    if path.startswith(base + "/"):
        return path[len(base) + 1:]
    if path.startswith(HOME + "/"):
        return "~/" + path[len(HOME) + 1:]
    return path


def open_path(path):
    fm = cfg["file_manager"].strip()
    try:
        if fm and os.path.isdir(path):
            subprocess.Popen(shlex.split(fm) + [path])
        else:
            Gio.AppInfo.launch_default_for_uri(GLib.filename_to_uri(path, None), None)
    except (GLib.Error, OSError) as err:
        print("cd: could not open", path, err, file=sys.stderr)


def reveal(path):
    """Open the parent folder with the item selected (file manager DBus API)."""
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        bus.call_sync(
            "org.freedesktop.FileManager1", "/org/freedesktop/FileManager1",
            "org.freedesktop.FileManager1", "ShowItems",
            GLib.Variant("(ass)", ([GLib.filename_to_uri(path, None)], "")),
            None, Gio.DBusCallFlags.NONE, 1500, None)
    except GLib.Error:
        open_path(os.path.dirname(path))


def icon_for(path, is_dir):
    ctype = "inode/directory" if is_dir else Gio.content_type_guess(path, None)[0]
    return Gio.content_type_get_symbolic_icon(ctype)


def render_pdf(path):
    import cairo
    doc = Poppler.Document.new_from_file(GLib.filename_to_uri(path, None), None)
    page = doc.get_page(0)
    w, h = page.get_size()
    scale = 2.0
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(w * scale), int(h * scale))
    ctx = cairo.Context(surf)
    ctx.set_source_rgb(1, 1, 1)
    ctx.paint()
    ctx.scale(scale, scale)
    page.render(ctx)
    return Gdk.MemoryTexture.new(
        surf.get_width(), surf.get_height(), Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED,
        GLib.Bytes.new(bytes(surf.get_data())), surf.get_stride())


# --------------------------------------------------------------------------
# launcher window
# --------------------------------------------------------------------------
# id: (label, dark?, bg, surface, fg, muted, accent, text-on-accent)
THEMES = {
    "gruvbox-dark":     ("Gruvbox Dark",     True,  "#282828", "#3c3836", "#ebdbb2", "#a89984", "#fabd2f", "#282828"),
    "gruvbox-light":    ("Gruvbox Light",    False, "#fbf1c7", "#ebdbb2", "#3c3836", "#7c6f64", "#d79921", "#fbf1c7"),
    "catppuccin-mocha": ("Catppuccin Mocha", True,  "#1e1e2e", "#313244", "#cdd6f4", "#a6adc8", "#cba6f7", "#1e1e2e"),
    "catppuccin-macchiato": ("Catppuccin Macchiato", True, "#24273a", "#363a4f", "#cad3f5", "#a5adcb", "#c6a0f6", "#24273a"),
    "catppuccin-frappe": ("Catppuccin Frappe", True, "#303446", "#414559", "#c6d0f5", "#a5adce", "#ca9ee6", "#303446"),
    "catppuccin-latte": ("Catppuccin Latte", False, "#eff1f5", "#ccd0da", "#4c4f69", "#6c6f85", "#8839ef", "#eff1f5"),
    "nord":             ("Nord",             True,  "#2e3440", "#3b4252", "#eceff4", "#9aa5b8", "#88c0d0", "#2e3440"),
    "dracula":          ("Dracula",          True,  "#282a36", "#343746", "#f8f8f2", "#a9adc4", "#bd93f9", "#282a36"),
    "tokyo-night":      ("Tokyo Night",      True,  "#1a1b26", "#24283b", "#c0caf5", "#7982a9", "#7aa2f7", "#1a1b26"),
    "rose-pine":        ("Rose Pine",        True,  "#191724", "#1f1d2e", "#e0def4", "#908caa", "#c4a7e7", "#191724"),
}

CSS_TEMPLATE = """
window.cd-win, window.cd-win.background, window.cd-win.csd {
    background-color: transparent; background-image: none; box-shadow: none;
}
.cd-card {
    background-color: %(bg)s; color: %(fg)s; border-radius: 16px;
    border: 1px solid %(border)s; box-shadow: 0 8px 28px rgba(0, 0, 0, 0.35);
}
.cd-input-card { padding: 8px 10px; }
.cd-list-card { padding: 8px; }
entry.cd-entry {
    font-size: 20px; padding: 8px 12px; min-height: 30px; color: %(fg)s;
    background: none; border: none; box-shadow: none; outline: none; caret-color: %(accent)s;
}
entry.cd-entry text placeholder { color: %(muted)s; }
button.cd-gear { color: %(muted)s; }
list.cd-list { background: none; }
row.cd-row { padding: 7px 10px; border-radius: 10px; color: %(fg)s; }
row.cd-row:hover { background-color: %(surface)s; }
row.cd-row:selected { background-color: %(accent)s; color: %(on_accent)s; }
.cd-dim { color: %(muted)s; font-size: 0.9em; }
row.cd-row:selected .cd-dim { color: %(on_accent)s; opacity: 0.7; }
.cd-preview { background-color: %(surface)s; border-radius: 12px; }
"""


def build_css(theme):
    if theme in THEMES:
        _l, _d, bg, surface, fg, muted, accent, on_accent = THEMES[theme]
        colors = dict(bg=bg, surface=surface, fg=fg, muted=muted, accent=accent,
                      on_accent=on_accent, border=surface)
    else:  # system / light / dark: use libadwaita's own colours
        colors = dict(bg="@window_bg_color", surface="alpha(@window_fg_color, 0.08)",
                      fg="@window_fg_color", muted="alpha(@window_fg_color, 0.55)",
                      accent="@accent_bg_color", on_accent="@accent_fg_color",
                      border="alpha(@window_fg_color, 0.12)")
    return CSS_TEMPLATE % colors

TRANSITIONS = {
    "slide": (Gtk.RevealerTransitionType.SLIDE_DOWN, Gtk.RevealerTransitionType.SLIDE_LEFT),
    "fade": (Gtk.RevealerTransitionType.CROSSFADE, Gtk.RevealerTransitionType.CROSSFADE),
    "swing": (Gtk.RevealerTransitionType.SWING_DOWN, Gtk.RevealerTransitionType.SWING_LEFT),
}


class CdWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, resizable=False, title="cd")
        self._prev_id = 0
        self._was_active = False
        self.add_css_class("cd-win")

        self.root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                            margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        self.set_content(self.root)

        # card 1: the input
        input_card = Gtk.Box(spacing=6)
        input_card.add_css_class("cd-card")
        input_card.add_css_class("cd-input-card")
        self.entry = Gtk.Entry(placeholder_text="cd", hexpand=True)
        self.entry.add_css_class("cd-entry")
        self.entry.connect("changed", self.on_changed)
        input_card.append(self.entry)
        gear = Gtk.Button(icon_name="emblem-system-symbolic", tooltip_text="Settings (Ctrl+,)",
                          valign=Gtk.Align.CENTER)
        gear.add_css_class("flat")
        gear.add_css_class("cd-gear")
        gear.connect("clicked", lambda _b: app.show_settings())
        input_card.append(gear)
        self.root.append(input_card)

        # card 2: suggestions (+ preview), slides in under the input
        self.revealer = Gtk.Revealer()
        self.root.append(self.revealer)
        list_card = Gtk.Box(margin_top=8)
        list_card.add_css_class("cd-card")
        list_card.add_css_class("cd-list-card")
        self.revealer.set_child(list_card)

        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.listbox.add_css_class("cd-list")
        self.listbox.connect("row-selected", self.on_row_selected)
        self.listbox.connect("row-activated", lambda _l, r: self.open_target(r.path, r.is_dir, False))
        self.scroller = Gtk.ScrolledWindow(hexpand=True, propagate_natural_height=True,
                                           max_content_height=340,
                                           hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.scroller.set_child(self.listbox)
        list_card.append(self.scroller)

        self.preview_revealer = Gtk.Revealer(hexpand=False)
        # The pane's size comes from an empty box; the picture is an overlay that is
        # never measured, so a big image can't stretch the pane.
        pbox = Gtk.Overlay(margin_start=10, hexpand=False, vexpand=False, valign=Gtk.Align.START)
        pbox.add_css_class("cd-preview")
        pbox.set_overflow(Gtk.Overflow.HIDDEN)
        pbox.set_child(Gtk.Box(width_request=250, height_request=400))
        self.preview = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, can_shrink=True)
        pbox.add_overlay(self.preview)
        pbox.set_clip_overlay(self.preview, True)
        self.preview_revealer.set_child(pbox)
        list_card.append(self.preview_revealer)

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.on_key)
        self.entry.add_controller(keys)

        self.connect("close-request", lambda _w: (self.hide_launcher(), True)[1])
        self.connect("notify::is-active", self.on_active_changed)
        self.apply_config()

    # -- config / visibility
    def apply_config(self):
        # fixed size: the window never resizes, so the input stays at the same y
        self.root.set_size_request(int(cfg["width"]) - 36, 444)
        vert, horiz = TRANSITIONS.get(cfg["animation"], TRANSITIONS["slide"])
        ms = int(cfg["animation_ms"])
        self.revealer.set_transition_type(vert)
        self.revealer.set_transition_duration(ms)
        self.preview_revealer.set_transition_type(horiz)
        self.preview_revealer.set_transition_duration(ms)
        if not cfg["preview"]:
            self.preview_revealer.set_reveal_child(False)

    def show_launcher(self):
        self.entry.set_text("")
        self.revealer.set_reveal_child(False)
        self.preview_revealer.set_reveal_child(False)
        self.present()
        self.entry.grab_focus()

    def hide_launcher(self):
        self.set_visible(False)

    def on_active_changed(self, *_):
        if self.is_active():
            self._was_active = True
        elif self._was_active:
            self._was_active = False
            if cfg["close_on_focus_loss"] and self.get_visible():
                self.hide_launcher()

    # -- suggestions
    def on_changed(self, entry):
        text = entry.get_text()
        matches = list_matches(text) if text.strip() else []
        child = self.listbox.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.listbox.remove(child)
            child = nxt
        for path, is_dir in matches:
            self.listbox.append(self.make_row(path, is_dir))
        self.revealer.set_reveal_child(bool(matches))
        if matches:
            self.listbox.select_row(self.listbox.get_row_at_index(0))
            self.scroller.get_vadjustment().set_value(0)
        else:
            self.preview_revealer.set_reveal_child(False)

    def make_row(self, path, is_dir):
        row = Gtk.ListBoxRow()
        row.add_css_class("cd-row")
        row.path, row.is_dir = path, is_dir
        box = Gtk.Box(spacing=10)
        box.append(Gtk.Image.new_from_gicon(icon_for(path, is_dir)))
        name = os.path.basename(path) + ("/" if is_dir else "")
        box.append(Gtk.Label(label=name, xalign=0, hexpand=True, ellipsize=3))
        where = Gtk.Label(label=os.path.dirname(path).replace(HOME, "~"), ellipsize=1)
        where.add_css_class("cd-dim")
        box.append(where)
        row.set_child(box)
        return row

    def move_selection(self, delta):
        row = self.listbox.get_selected_row()
        nxt = self.listbox.get_row_at_index((row.get_index() if row else -1) + delta)
        if not nxt:
            return
        self.listbox.select_row(nxt)
        ok, rect = nxt.compute_bounds(self.listbox)
        if ok:
            adj = self.scroller.get_vadjustment()
            y, h = rect.get_y(), rect.get_height()
            if y < adj.get_value():
                adj.set_value(y)
            elif y + h > adj.get_value() + adj.get_page_size():
                adj.set_value(y + h - adj.get_page_size())

    # -- keyboard
    def on_key(self, _c, keyval, _code, state):
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        if keyval == Gdk.KEY_Escape:
            self.hide_launcher()
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.activate_selected(alt=ctrl)
        elif keyval == Gdk.KEY_Down:
            self.move_selection(1)
        elif keyval == Gdk.KEY_Up:
            self.move_selection(-1)
        elif keyval == Gdk.KEY_Tab:
            row = self.listbox.get_selected_row()
            if row:
                self.entry.set_text(shorten(row.path) + ("/" if row.is_dir else ""))
                self.entry.set_position(-1)
        elif ctrl and keyval == Gdk.KEY_comma:
            self.get_application().show_settings()
        else:
            return False
        return True

    def activate_selected(self, alt=False):
        row = self.listbox.get_selected_row()
        if row:
            self.open_target(row.path, row.is_dir, alt)
            return
        path = resolve_dir(absolute(self.entry.get_text()))
        if path and os.path.exists(path):
            self.open_target(path, os.path.isdir(path), alt)

    def open_target(self, path, is_dir, alt):
        if is_dir:
            open_path(path)
        else:
            mode = cfg["enter_on_file"]
            if alt:
                mode = "reveal" if mode == "open" else "open"
            reveal(path) if mode == "reveal" else open_path(path)
        self.hide_launcher()

    # -- preview (debounced so typing stays smooth)
    def on_row_selected(self, _lb, row):
        if self._prev_id:
            GLib.source_remove(self._prev_id)
            self._prev_id = 0
        if not row or not cfg["preview"]:
            self.preview_revealer.set_reveal_child(False)
            return
        self._prev_id = GLib.timeout_add(120, self._do_preview, row.path)

    def _do_preview(self, path):
        self._prev_id = 0
        ext = os.path.splitext(path)[1].lower()
        texture = None
        try:
            if ext in IMAGE_EXT:
                texture = Gdk.Texture.new_from_filename(path)
            elif ext == ".pdf" and HAVE_POPPLER:
                texture = render_pdf(path)
        except Exception:
            texture = None
        self.preview.set_paintable(texture)
        self.preview_revealer.set_reveal_child(texture is not None)
        return GLib.SOURCE_REMOVE


# --------------------------------------------------------------------------
# settings window
# --------------------------------------------------------------------------
class SettingsWindow(Adw.PreferencesWindow):
    def __init__(self, app):
        super().__init__(application=app, title="cd - Settings",
                         default_width=560, default_height=760)
        self.app = app
        page = Adw.PreferencesPage()
        self.add(page)

        # shortcut
        g = Adw.PreferencesGroup(title="Shortcut")
        page.add(g)
        row = Adw.ActionRow(title="Open cd",
                            subtitle="Saved as a custom shortcut in GNOME keyboard settings")
        self.shortcut_btn = Gtk.Button(label=accel_label(cfg["shortcut"]), valign=Gtk.Align.CENTER)
        self.shortcut_btn.connect("clicked", self.capture_shortcut)
        row.add_suffix(self.shortcut_btn)
        g.add(row)

        # search
        g = Adw.PreferencesGroup(title="Search")
        page.add(g)
        self.entry_row(g, "Start folder", "start_dir", "Relative paths are resolved from here")
        self.switch_row(g, "Show files", "Suggest files as well as folders", "show_files")
        self.switch_row(g, "Show hidden files", "Include names starting with a dot", "show_hidden")
        self.switch_row(g, "Folders first", "List folders above files", "folders_first")
        self.switch_row(g, "Match anywhere in name", "'tele' finds 'my-telegram', not just 'telegram'", "match_anywhere")
        self.spin_row(g, "Max suggestions", "max_results", 5, 100, 5)

        # opening
        g = Adw.PreferencesGroup(title="Opening")
        page.add(g)
        self.combo_row(g, "Enter on a file", "enter_on_file",
                       [("open", "Open the file"), ("reveal", "Show it in its folder")],
                       "Ctrl+Enter does the opposite")
        self.entry_row(g, "File manager command", "file_manager", "Empty = system default, e.g. nautilus")

        # look
        g = Adw.PreferencesGroup(title="Look & feel")
        page.add(g)
        self.switch_row(g, "Preview images and PDFs", "Shown beside the suggestions", "preview")
        self.switch_row(g, "Close when focus is lost", "", "close_on_focus_loss")
        self.combo_row(g, "Animation", "animation",
                       [("slide", "Slide"), ("fade", "Fade"), ("swing", "Swing")])
        self.spin_row(g, "Animation speed (ms)", "animation_ms", 0, 800, 20)
        self.spin_row(g, "Width (px)", "width", 400, 1400, 20)
        self.combo_row(g, "Theme", "theme",
                       [("system", "Follow system"), ("light", "Light"), ("dark", "Dark")]
                       + [(k, v[0]) for k, v in THEMES.items()])

    # -- helpers
    def changed(self, key, value):
        cfg.set(key, value)
        self.app.apply_config()

    def switch_row(self, group, title, subtitle, key):
        r = Adw.SwitchRow(title=title, subtitle=subtitle, active=cfg[key])
        r.connect("notify::active", lambda w, _p: self.changed(key, w.get_active()))
        group.add(r)

    def spin_row(self, group, title, key, lo, hi, step):
        r = Adw.SpinRow.new_with_range(lo, hi, step)
        r.set_title(title)
        r.set_value(cfg[key])
        r.connect("notify::value", lambda w, _p: self.changed(key, int(w.get_value())))
        group.add(r)

    def combo_row(self, group, title, key, options, subtitle=""):
        values = [v for v, _l in options]
        r = Adw.ComboRow(title=title, subtitle=subtitle,
                         model=Gtk.StringList.new([l for _v, l in options]))
        if cfg[key] in values:
            r.set_selected(values.index(cfg[key]))
        r.connect("notify::selected", lambda w, _p: self.changed(key, values[w.get_selected()]))
        group.add(r)

    def entry_row(self, group, title, key, subtitle=""):
        r = Adw.EntryRow(title=title + (" - " + subtitle if subtitle else ""), text=cfg[key])
        r.connect("changed", lambda w: self.changed(key, w.get_text()))
        group.add(r)

    # -- shortcut capture
    def capture_shortcut(self, _btn):
        dlg = Gtk.Window(modal=True, transient_for=self, title="Set shortcut",
                         default_width=360, default_height=140)
        label = Gtk.Label(label="Press the new shortcut...\nEsc to cancel", justify=Gtk.Justification.CENTER)
        dlg.set_child(label)
        keys = Gtk.EventControllerKey()
        modifiers = {Gdk.KEY_Control_L, Gdk.KEY_Control_R, Gdk.KEY_Alt_L, Gdk.KEY_Alt_R,
                     Gdk.KEY_Shift_L, Gdk.KEY_Shift_R, Gdk.KEY_Super_L, Gdk.KEY_Super_R,
                     Gdk.KEY_Meta_L, Gdk.KEY_Meta_R, Gdk.KEY_ISO_Level3_Shift}

        def on_key(_c, keyval, _code, state):
            if keyval in modifiers:
                return True
            mods = state & Gtk.accelerator_get_default_mod_mask()
            if keyval == Gdk.KEY_Escape and not mods:
                dlg.close()
                return True
            if not mods:
                label.set_text("Add a modifier (Ctrl, Alt, Super)...\nEsc to cancel")
                return True
            accel = Gtk.accelerator_name(Gdk.keyval_to_lower(keyval), mods)
            cfg.set("shortcut", accel)
            try:
                apply_shortcut(accel)
                self.add_toast(Adw.Toast(title="Shortcut set to " + accel_label(accel)))
            except Exception as err:  # not GNOME / schema missing
                self.add_toast(Adw.Toast(title="Could not set shortcut: %s" % err))
            self.shortcut_btn.set_label(accel_label(accel))
            dlg.close()
            return True

        keys.connect("key-pressed", on_key)
        dlg.add_controller(keys)
        dlg.present()


# --------------------------------------------------------------------------
# application
# --------------------------------------------------------------------------
class CdApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.win = None
        self.settings_win = None

    def do_startup(self):
        Adw.Application.do_startup(self)
        self.hold()  # keep running hidden, so the shortcut opens instantly
        self.css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.apply_theme()

    def do_command_line(self, cl):
        args = cl.get_arguments()[1:]
        if "--quit" in args:
            self.quit()
        elif "--settings" in args:
            self.show_settings()
        elif "--background" in args:
            self.ensure_window()
        else:
            self.ensure_window().show_launcher()
        return 0

    def ensure_window(self):
        if not self.win:
            self.win = CdWindow(self)
        return self.win

    def show_settings(self):
        if not self.settings_win:
            self.settings_win = SettingsWindow(self)
            self.settings_win.connect("close-request", self._settings_closed)
        self.settings_win.present()

    def _settings_closed(self, _w):
        self.settings_win = None
        return False

    def apply_theme(self):
        theme = cfg["theme"]
        self.css.load_from_data(build_css(theme).encode())
        if theme in THEMES:
            scheme = Adw.ColorScheme.FORCE_DARK if THEMES[theme][1] else Adw.ColorScheme.FORCE_LIGHT
        else:
            scheme = {"light": Adw.ColorScheme.FORCE_LIGHT,
                      "dark": Adw.ColorScheme.FORCE_DARK}.get(theme, Adw.ColorScheme.DEFAULT)
        Adw.StyleManager.get_default().set_color_scheme(scheme)

    def apply_config(self):
        self.apply_theme()
        if self.win:
            self.win.apply_config()


if __name__ == "__main__":
    if "--apply-shortcut" in sys.argv:
        apply_shortcut(cfg["shortcut"])
        print("Shortcut set:", accel_label(cfg["shortcut"]))
        sys.exit(0)
    if "--remove-shortcut" in sys.argv:
        remove_shortcut()
        sys.exit(0)
    sys.exit(CdApp().run(sys.argv))
