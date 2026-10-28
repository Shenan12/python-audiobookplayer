import io
import math
import os
import re
import sys
import time
import struct
import sqlite3
import hashlib
import traceback
import tkinter as tk
import tkinter.font as tkfont
from bisect import bisect_right
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk

APP_DIR = Path.home() / ".m4b_player"
DB_PATH = APP_DIR / "library.db"
LOG_PATH = APP_DIR / "error.log"
COVER_DIR = APP_DIR / "covers"
ICO_PATH = APP_DIR / "audiobook.ico"


def log_error():
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n" + traceback.format_exc() + "\n")
    except Exception:
        pass


def fatal(title, message):
    r = tk.Tk()
    r.withdraw()
    messagebox.showerror(title, message)
    r.destroy()
    sys.exit(1)


try:
    import vlc
except Exception as e:
    fatal(
        "VLC could not be loaded",
        f"{e}\n\nMake sure VLC is installed, and that Python and VLC are both 64-bit "
        "(or both 32-bit).\nIf the package is missing, open Command Prompt and run:\n"
        "pip install python-vlc",
    )

try:
    import customtkinter as ctk
    from mutagen.mp4 import MP4, MP4Cover
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError as e:
    fatal(
        "Missing package",
        f"{e}\n\nOpen Command Prompt once and run:\npip install python-vlc mutagen pillow customtkinter",
    )

RESAMPLE = getattr(Image, "Resampling", Image).LANCZOS

DARK = {
    "BG": "#0c0c10", "PANEL": "#15151b", "PANEL2": "#1f1f29", "PANEL3": "#2b2b38",
    "TEXT": "#f1f0f7", "MUTED": "#8b8a9b", "TRACK": "#34343f", "RAW": "#5c5b6b",
}
LIGHT = {
    "BG": "#e4e4ec", "PANEL": "#ffffff", "PANEL2": "#eeeef5", "PANEL3": "#dcdce8",
    "TEXT": "#1a1a24", "MUTED": "#6b6a7b", "TRACK": "#cfcfdb", "RAW": "#9a99a8",
}
DEFAULT_ACCENT = "#8b6cff"
ACCENT_PRESETS = [
    ("Purple", "#8b6cff"), ("Blue", "#3b82f6"), ("Teal", "#14b8a6"), ("Green", "#22c55e"),
    ("Orange", "#f97316"), ("Pink", "#ec4899"), ("Red", "#ef4444"),
]

# Palette names, assigned by set_palette(). The UI looks them up by name (see apply_opts), so
# changing the theme or accent only needs set_palette() followed by App.apply_theme().
BG = PANEL = PANEL2 = PANEL3 = TEXT = MUTED = TRACK = RAW = ""
ACCENT = ACCENT_HOVER = ACCENT_DEEP = ACCENT_TEXT = ON_ACCENT = KNOB = KNOB_HOVER = SEL_TEXT = ""

FONT = "Segoe UI"

LIB_MIN, LIB_MAX, LIB_DEFAULT = 280, 600, 320
PANEL_MIN, PANEL_MAX, PANEL_DEFAULT = 300, 900, 390
HERO_MIN = 340


def _rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(v))) for v in rgb)


def mix(a, b, t):
    ra, rb = _rgb(a), _rgb(b)
    return _hex([ra[i] + (rb[i] - ra[i]) * t for i in range(3)])


def _luminance(c):
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(c)
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(a, b):
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def readable_on(color, bg, toward, target=4.5):
    for _ in range(20):
        if contrast(color, bg) >= target:
            break
        color = mix(color, toward, 0.1)
    return color


def valid_hex(value, default=DEFAULT_ACCENT):
    return value.lower() if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value) else default


def set_palette(mode, accent):
    global BG, PANEL, PANEL2, PANEL3, TEXT, MUTED, TRACK, RAW
    global ACCENT, ACCENT_HOVER, ACCENT_DEEP, ACCENT_TEXT, ON_ACCENT, KNOB, KNOB_HOVER, SEL_TEXT
    dark = mode != "light"
    p = DARK if dark else LIGHT
    BG, PANEL, PANEL2, PANEL3 = p["BG"], p["PANEL"], p["PANEL2"], p["PANEL3"]
    TEXT, MUTED, TRACK, RAW = p["TEXT"], p["MUTED"], p["TRACK"], p["RAW"]
    ACCENT = accent
    if dark:
        ACCENT_HOVER = mix(accent, "#ffffff", 0.2)
        ACCENT_TEXT = readable_on(ACCENT_HOVER, PANEL, "#ffffff")
        ACCENT_DEEP = mix(PANEL, accent, 0.23)
        KNOB, KNOB_HOVER = "#ffffff", mix(accent, "#ffffff", 0.85)
        SEL_TEXT = "#ffffff"
    else:
        ACCENT_HOVER = mix(accent, "#000000", 0.15)
        ACCENT_TEXT = readable_on(accent, PANEL, "#000000")
        ACCENT_DEEP = mix(PANEL, accent, 0.16)
        KNOB, KNOB_HOVER = ACCENT_HOVER, mix(accent, "#000000", 0.3)
        SEL_TEXT = TEXT
    ON_ACCENT = "#ffffff" if contrast(accent, "#ffffff") >= 2.6 else "#14141c"


def apply_opts(widget, opts):
    """Configure a widget from {option: palette name}; values that are not palette names pass through."""
    widget.configure(**{k: globals().get(v, v) for k, v in opts.items()})


def load_look(store):
    mode = store.get_setting("theme", "dark")
    return ("light" if mode == "light" else "dark"), valid_hex(store.get_setting("accent"))


set_palette("dark", DEFAULT_ACCENT)

TAG_NAMES = {
    "\xa9nam": "Title",
    "\xa9ART": "Author / Artist",
    "aART": "Album artist",
    "\xa9alb": "Album",
    "\xa9wrt": "Composer",
    "\xa9gen": "Genre",
    "\xa9day": "Year",
    "desc": "Description",
    "ldes": "Long description",
    "\xa9cmt": "Comment",
    "\xa9grp": "Grouping",
    "cprt": "Copyright",
    "\xa9too": "Encoder",
    "trkn": "Track",
    "disk": "Disc",
    "stik": "Media kind",
    "pgap": "Gapless playback",
    "cpil": "Compilation",
    "tmpo": "Tempo",
    "\xa9lyr": "Lyrics",
    "sonm": "Sort title",
    "soar": "Sort artist",
    "soal": "Sort album",
    "purd": "Purchase date",
    "catg": "Category",
    "keyw": "Keywords",
}


def fmt_time(ms):
    s = max(0, int(ms // 1000))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}"


def percent(pos, dur):
    return int(min(100, pos * 100 / dur)) if dur else 0


def fmt_value(v):
    if isinstance(v, MP4Cover):
        return f"image, {len(v) // 1024} KB"
    if isinstance(v, (list, tuple)):
        if isinstance(v, tuple) and len(v) == 2 and all(isinstance(x, int) for x in v):
            return str(v[0]) if v[1] == 0 else f"{v[0]} / {v[1]}"
        return ", ".join(fmt_value(x) for x in v)
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    if isinstance(v, bool):
        return "Yes" if v else "No"
    return str(v)


def fit_text(text, font, max_px):
    if font.measure(text) <= max_px:
        return text
    t = text
    while t and font.measure(t + "...") > max_px:
        t = t[:-1]
    return t.rstrip() + "..."


# ---------- images and icons ----------
def round_corners(img, radius):
    try:
        img = img.convert("RGBA")
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, img.size[0] - 1, img.size[1] - 1], radius=radius, fill=255)
        img.putalpha(mask)
    except Exception:
        pass
    return img


def placeholder_image(size, radius, label=True, fill=None):
    img = Image.new("RGBA", (size, size), fill or PANEL2)
    if label:
        d = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("segoeui.ttf", max(size // 9, 8))
        except Exception:
            font = ImageFont.load_default()
        text = "No cover"
        try:
            box = d.textbbox((0, 0), text, font=font)
            w, h = box[2] - box[0], box[3] - box[1]
        except Exception:
            w, h = 50, 10
        d.text(((size - w) // 2, (size - h) // 2 - 2), text, fill=MUTED, font=font)
    return round_corners(img, radius)


def cover_image(data, box, radius):
    img = None
    if data:
        try:
            raw = Image.open(io.BytesIO(data)).convert("RGB")
            scale = min(box * 2 / raw.width, box * 2 / raw.height)
            raw = raw.resize((max(int(raw.width * scale), 1), max(int(raw.height * scale), 1)), RESAMPLE)
            img = round_corners(raw, radius * 2)
        except Exception:
            img = None
    if img is None:
        img = placeholder_image(box * 2, radius * 2)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(img.width // 2, img.height // 2))


def read_cover(path):
    try:
        tags = MP4(path).tags
        covers = tags.get("covr") if tags else None
        if covers:
            return bytes(covers[0])
    except Exception:
        pass
    return None


def placeholder_thumb():
    img = placeholder_image(96, 18, label=False, fill=PANEL3)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(48, 48))


def list_thumb(path):
    """Returns (image, is_placeholder); placeholders are theme coloured and get rebuilt on theme change."""
    key = hashlib.sha1(path.encode("utf-8")).hexdigest()
    cache = COVER_DIR / (key + ".png")
    img = None
    try:
        if cache.exists():
            img = Image.open(cache).convert("RGBA")
    except Exception:
        img = None
    if img is None:
        data = read_cover(path)
        if data:
            try:
                raw = Image.open(io.BytesIO(data)).convert("RGB")
                raw = ImageOps.fit(raw, (96, 96), RESAMPLE)
                img = round_corners(raw, 18)
                COVER_DIR.mkdir(parents=True, exist_ok=True)
                img.save(cache)
            except Exception:
                img = None
    if img is None:
        return placeholder_thumb(), True
    return ctk.CTkImage(light_image=img, dark_image=img, size=(48, 48)), False


def make_icon(kind, size, color="#ffffff"):
    big = 192
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = color
    s = big
    if kind == "play":
        d.polygon([(s * 0.32, s * 0.16), (s * 0.32, s * 0.84), (s * 0.86, s * 0.50)], fill=c)
    elif kind == "pause":
        d.rectangle([s * 0.24, s * 0.18, s * 0.42, s * 0.82], fill=c)
        d.rectangle([s * 0.58, s * 0.18, s * 0.76, s * 0.82], fill=c)
    elif kind == "prev":
        d.rectangle([s * 0.16, s * 0.20, s * 0.28, s * 0.80], fill=c)
        d.polygon([(s * 0.84, s * 0.18), (s * 0.84, s * 0.82), (s * 0.36, s * 0.50)], fill=c)
    elif kind == "next":
        d.rectangle([s * 0.72, s * 0.20, s * 0.84, s * 0.80], fill=c)
        d.polygon([(s * 0.16, s * 0.18), (s * 0.16, s * 0.82), (s * 0.64, s * 0.50)], fill=c)
    elif kind == "volume":
        d.polygon([(s * 0.10, s * 0.38), (s * 0.28, s * 0.38), (s * 0.48, s * 0.20),
                   (s * 0.48, s * 0.80), (s * 0.28, s * 0.62), (s * 0.10, s * 0.62)], fill=c)
        d.arc([s * 0.34, s * 0.34, s * 0.68, s * 0.66], -55, 55, fill=c, width=int(s * 0.07))
        d.arc([s * 0.30, s * 0.18, s * 0.90, s * 0.82], -55, 55, fill=c, width=int(s * 0.07))
    elif kind == "gear":
        mid = s / 2
        for k in range(8):
            a = math.radians(k * 45)
            ux, uy = math.cos(a), math.sin(a)
            px, py = -uy, ux
            r0, r1, hw = s * 0.30, s * 0.44, s * 0.075
            d.polygon([(mid + ux * r0 + px * hw, mid + uy * r0 + py * hw),
                       (mid + ux * r1 + px * hw, mid + uy * r1 + py * hw),
                       (mid + ux * r1 - px * hw, mid + uy * r1 - py * hw),
                       (mid + ux * r0 - px * hw, mid + uy * r0 - py * hw)], fill=c)
        d.ellipse([mid - s * 0.34, mid - s * 0.34, mid + s * 0.34, mid + s * 0.34], fill=c)
        d.ellipse([mid - s * 0.15, mid - s * 0.15, mid + s * 0.15, mid + s * 0.15], fill=(0, 0, 0, 0))
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))


def draw_app_icon(size=512):
    top = (162, 138, 255)
    bottom = (98, 66, 226)
    grad = Image.new("RGBA", (size, size))
    gd = ImageDraw.Draw(grad)
    for y in range(size):
        t = y / (size - 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,)
        gd.line([(0, y), (size, y)], fill=color)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=int(size * 0.22), fill=255)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    k = size / 512
    white = "#ffffff"
    d.arc([112 * k, 100 * k, 400 * k, 388 * k], 180, 360, fill=white, width=int(36 * k))
    d.rounded_rectangle([92 * k, 236 * k, 168 * k, 380 * k], radius=int(28 * k), fill=white)
    d.rounded_rectangle([344 * k, 236 * k, 420 * k, 380 * k], radius=int(28 * k), fill=white)
    return img


def ensure_icon():
    try:
        if not ICO_PATH.exists():
            APP_DIR.mkdir(parents=True, exist_ok=True)
            draw_app_icon(512).save(
                ICO_PATH, format="ICO",
                sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        return str(ICO_PATH)
    except Exception:
        log_error()
        return None


# ---------- QuickTime chapter track reader ----------
def _atoms(f, start, end):
    pos = start
    while pos + 8 <= end:
        f.seek(pos)
        hdr = f.read(8)
        if len(hdr) < 8:
            return
        size, typ = struct.unpack(">I4s", hdr)
        hlen = 8
        if size == 1:
            ext = f.read(8)
            if len(ext) < 8:
                return
            size = struct.unpack(">Q", ext)[0]
            hlen = 16
        elif size == 0:
            size = end - pos
        if size < hlen:
            return
        yield typ, pos + hlen, min(pos + size, end)
        pos += size


def _child(f, start, end, name):
    for typ, ds, de in _atoms(f, start, end):
        if typ == name:
            return ds, de
    return None


def _path(f, start, end, names):
    cur = (start, end)
    for n in names:
        cur = _child(f, cur[0], cur[1], n)
        if cur is None:
            return None
    return cur


def _read(f, box, limit=None):
    f.seek(box[0])
    n = box[1] - box[0]
    if limit is not None:
        n = min(n, limit)
    return f.read(n)


def _decode_text(raw):
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be", "replace")
    if raw.startswith(b"\xff\xfe"):
        return raw[2:].decode("utf-16-le", "replace")
    return raw.decode("utf-8", "replace")


def read_text_track(f, t):
    ds, de = t["box"]
    stbl = _path(f, ds, de, [b"mdia", b"minf", b"stbl"])
    if stbl is None:
        return []
    stts = _child(f, stbl[0], stbl[1], b"stts")
    stsz = _child(f, stbl[0], stbl[1], b"stsz")
    stsc = _child(f, stbl[0], stbl[1], b"stsc")
    stco = _child(f, stbl[0], stbl[1], b"stco")
    co64 = _child(f, stbl[0], stbl[1], b"co64")
    if not (stts and stsz and stsc and (stco or co64)):
        return []

    d = _read(f, stsz)
    default_size, count = struct.unpack(">II", d[4:12])
    if count > 20000:
        return []
    if default_size:
        sizes = [default_size] * count
    else:
        sizes = list(struct.unpack(">%dI" % count, d[12:12 + 4 * count]))

    d = _read(f, stts)
    n = struct.unpack(">I", d[4:8])[0]
    deltas = []
    for i in range(n):
        c, dl = struct.unpack(">II", d[8 + 8 * i:16 + 8 * i])
        deltas.extend([dl] * c)
        if len(deltas) > 20000:
            return []
    starts = []
    acc = 0
    for i in range(count):
        starts.append(acc)
        acc += deltas[i] if i < len(deltas) else 0

    d = _read(f, stsc)
    n = struct.unpack(">I", d[4:8])[0]
    stsc_entries = [struct.unpack(">III", d[8 + 12 * i:20 + 12 * i]) for i in range(n)]

    if stco:
        d = _read(f, stco)
        n = struct.unpack(">I", d[4:8])[0]
        offsets = list(struct.unpack(">%dI" % n, d[8:8 + 4 * n]))
    else:
        d = _read(f, co64)
        n = struct.unpack(">I", d[4:8])[0]
        offsets = list(struct.unpack(">%dQ" % n, d[8:8 + 8 * n]))

    sample_offsets = []
    si = 0
    ei = 0
    for ci in range(len(offsets)):
        while ei + 1 < len(stsc_entries) and stsc_entries[ei + 1][0] <= ci + 1:
            ei += 1
        spc = stsc_entries[ei][1] if stsc_entries else 1
        off = offsets[ci]
        for _ in range(spc):
            if si >= count:
                break
            sample_offsets.append(off)
            off += sizes[si]
            si += 1

    ts = t["timescale"] or 1000
    chapters = []
    for i, off in enumerate(sample_offsets):
        if sizes[i] < 2:
            continue
        f.seek(off)
        raw = f.read(sizes[i])
        tlen = struct.unpack(">H", raw[:2])[0]
        title = _decode_text(raw[2:2 + tlen]).strip()
        ms = int(starts[i] * 1000 / ts)
        chapters.append((ms, title or f"Chapter {len(chapters) + 1}"))
    chapters.sort(key=lambda c: c[0])
    return chapters


def read_qt_chapters(path):
    layout = []
    with open(path, "rb") as f:
        size = os.path.getsize(path)
        moov = _child(f, 0, size, b"moov")
        if moov is None:
            return [], ["No moov atom found"]
        tracks = []
        for typ, ds, de in _atoms(f, moov[0], moov[1]):
            if typ != b"trak":
                continue
            info = {"box": (ds, de), "id": None, "handler": "?", "refs": [], "timescale": 1000}
            tkhd = _child(f, ds, de, b"tkhd")
            if tkhd:
                d = _read(f, tkhd, 32)
                if len(d) >= 24:
                    info["id"] = struct.unpack(">I", d[12:16] if d[0] == 0 else d[20:24])[0]
            hdlr = _path(f, ds, de, [b"mdia", b"hdlr"])
            if hdlr:
                d = _read(f, hdlr, 16)
                if len(d) >= 12:
                    info["handler"] = d[8:12].decode("latin-1")
            mdhd = _path(f, ds, de, [b"mdia", b"mdhd"])
            if mdhd:
                d = _read(f, mdhd, 32)
                if len(d) >= 24:
                    off = 12 if d[0] == 0 else 20
                    info["timescale"] = struct.unpack(">I", d[off:off + 4])[0] or 1000
            chap = _path(f, ds, de, [b"tref", b"chap"])
            if chap:
                d = _read(f, chap)
                info["refs"] = [struct.unpack(">I", d[i:i + 4])[0] for i in range(0, len(d) - 3, 4)]
            tracks.append(info)

        ref_ids = [r for t in tracks for r in t["refs"]]
        for t in tracks:
            tag = " (chapter track)" if t["id"] in ref_ids else ""
            layout.append(f"Track {t['id']}: {t['handler']}{tag}")

        candidates = [t for t in tracks if t["id"] in ref_ids]
        if not candidates:
            candidates = [t for t in tracks if t["handler"] in ("text", "sbtl", "subt")]
        for t in candidates:
            ch = read_text_track(f, t)
            if ch:
                return ch, layout
        return [], layout


def read_meta(path):
    meta = {
        "title": Path(path).stem,
        "author": "",
        "year": "",
        "duration_ms": 0,
        "chapters": [],
        "chapter_source": "",
        "scan": [],
        "cover": None,
        "tags": [],
        "tech": [],
    }
    try:
        audio = MP4(path)
    except Exception as e:
        meta["tech"] = [("File", os.path.basename(path)), ("Could not read tags", str(e))]
        return meta

    tags = audio.tags if audio.tags is not None else {}

    def first(key):
        v = tags.get(key)
        return fmt_value(v[0]).strip() if v else ""

    meta["title"] = first("\xa9nam") or first("\xa9alb") or meta["title"]
    meta["author"] = first("\xa9ART") or first("aART")
    meta["year"] = first("\xa9day")[:4]
    info = audio.info
    meta["duration_ms"] = int(getattr(info, "length", 0) * 1000)

    chaps = getattr(audio, "chapters", None)
    if chaps:
        try:
            found = [(int(c.start * 1000), c.title or f"Chapter {i}") for i, c in enumerate(chaps, 1)]
            found.sort(key=lambda c: c[0])
            meta["chapters"] = found
            if found:
                meta["chapter_source"] = "Nero chpl atom"
        except Exception:
            meta["chapters"] = []

    if not meta["chapters"]:
        try:
            qt, layout = read_qt_chapters(path)
            meta["scan"] = layout
            if qt:
                meta["chapters"] = qt
                meta["chapter_source"] = "QuickTime chapter track"
        except Exception as e:
            meta["scan"] = [f"Scan error: {e}"]
    if not meta["chapters"]:
        meta["chapter_source"] = "None found in file tags"

    covers = tags.get("covr")
    if covers:
        try:
            meta["cover"] = bytes(covers[0])
        except Exception:
            meta["cover"] = None

    order = {k: i for i, k in enumerate(TAG_NAMES)}
    for key in sorted(tags.keys(), key=lambda k: (order.get(k, 999), k)):
        if key == "covr":
            total = sum(len(bytes(c)) for c in tags[key])
            meta["tags"].append(("Cover art", f"{len(tags[key])} image(s), {total // 1024} KB", key))
            continue
        label = TAG_NAMES.get(key)
        if label is None:
            label = key.split(":")[-1] if key.startswith("----") else key
        meta["tags"].append((label, fmt_value(tags[key]), key))

    tech = [
        ("File", os.path.basename(path)),
        ("Folder", os.path.dirname(path)),
        ("File size", f"{os.path.getsize(path) / (1024 * 1024):.1f} MB"),
        ("Duration", fmt_time(meta["duration_ms"])),
        ("Chapters stored in file", str(len(meta["chapters"]))),
    ]
    codec = getattr(info, "codec_description", "") or getattr(info, "codec", "")
    if codec:
        tech.append(("Codec", str(codec)))
    if getattr(info, "bitrate", 0):
        tech.append(("Bitrate", f"{info.bitrate // 1000} kbps"))
    if getattr(info, "sample_rate", 0):
        tech.append(("Sample rate", f"{info.sample_rate} Hz"))
    if getattr(info, "channels", 0):
        tech.append(("Channels", str(info.channels)))
    if getattr(info, "bits_per_sample", 0):
        tech.append(("Bits per sample", str(info.bits_per_sample)))
    meta["tech"] = tech
    return meta


class Store:
    def __init__(self):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(DB_PATH)
        self.db.row_factory = sqlite3.Row
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS books ("
            "path TEXT PRIMARY KEY, title TEXT, author TEXT, "
            "duration_ms INTEGER DEFAULT 0, position_ms INTEGER DEFAULT 0, "
            "speed REAL DEFAULT 1.0, last_played REAL DEFAULT 0)"
        )
        self.db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        self.db.commit()

    def add(self, path, title, author, duration_ms):
        self.db.execute(
            "INSERT OR IGNORE INTO books (path, title, author, duration_ms) VALUES (?, ?, ?, ?)",
            (path, title, author, duration_ms),
        )
        self.db.commit()

    def all(self):
        return self.db.execute("SELECT * FROM books ORDER BY last_played DESC, title").fetchall()

    def get(self, path):
        return self.db.execute("SELECT * FROM books WHERE path = ?", (path,)).fetchone()

    def save_progress(self, path, pos, speed, dur):
        self.db.execute(
            "UPDATE books SET position_ms = ?, speed = ?, duration_ms = ?, last_played = ? WHERE path = ?",
            (int(pos), float(speed), int(dur), time.time(), path),
        )
        self.db.commit()

    def remove(self, path):
        self.db.execute("DELETE FROM books WHERE path = ?", (path,))
        self.db.commit()

    def get_setting(self, key, default=None):
        row = self.db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        self.db.commit()


def get_scale(root):
    try:
        s = float(root._get_window_scaling())
    except Exception:
        try:
            s = root.winfo_fpixels("1i") / 96.0
        except Exception:
            s = 1.0
    return min(max(s, 0.75), 4.0)


class Tooltip:
    def __init__(self, root, scale):
        self.root = root
        self.S = scale
        self.tip = None
        self.after_id = None

    def schedule(self, text, x, y, delay=350):
        self.hide()
        self.after_id = self.root.after(delay, lambda: self.show(text, x, y))

    def show(self, text, x, y):
        self.after_id = None
        self.destroy_tip()
        try:
            tip = tk.Toplevel(self.root)
            tip.wm_overrideredirect(True)
            try:
                tip.attributes("-topmost", True)
            except Exception:
                pass
            frame = tk.Frame(tip, bg=ACCENT_DEEP, padx=1, pady=1)
            frame.pack()
            tk.Label(frame, text=text, bg=PANEL3, fg=TEXT, font=(FONT, -int(round(13 * self.S))),
                     justify="left", wraplength=int(460 * self.S), padx=12, pady=7).pack()
            tip.update_idletasks()
            w, h = tip.winfo_reqwidth(), tip.winfo_reqheight()
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            x = max(min(x, sw - w - 8), 0)
            if y + h > sh - 8:
                y = max(y - h - 40, 0)
            tip.geometry(f"+{int(x)}+{int(y)}")
            self.tip = tip
        except Exception:
            self.tip = None

    def destroy_tip(self):
        if self.tip is not None:
            try:
                self.tip.destroy()
            except Exception:
                pass
            self.tip = None

    def hide(self):
        if self.after_id is not None:
            try:
                self.root.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None
        self.destroy_tip()


class Splitter(tk.Frame):
    """Thin draggable bar between two columns; reports horizontal drag distance in logical pixels."""

    def __init__(self, master, scale, begin, drag, end):
        super().__init__(master, bg=BG, width=max(int(10 * scale), 6), cursor="sb_h_double_arrow")
        self.S = scale
        self.begin, self.drag, self.end = begin, drag, end
        self.dragging = False
        self.x0 = 0
        self.grip = tk.Frame(self, bg=TRACK, width=max(int(3 * scale), 2), height=int(64 * scale))
        self.grip.place(relx=0.5, rely=0.5, anchor="center")
        for w in (self, self.grip):
            w.bind("<Enter>", self._enter)
            w.bind("<Leave>", self._leave)
            w.bind("<ButtonPress-1>", self._press)
            w.bind("<B1-Motion>", self._move)
            w.bind("<ButtonRelease-1>", self._release)

    def recolor(self):
        self.configure(bg=BG)
        self.grip.configure(bg=ACCENT if self.dragging else TRACK)

    def _enter(self, event=None):
        self.grip.configure(bg=ACCENT)

    def _leave(self, event=None):
        if not self.dragging:
            self.grip.configure(bg=TRACK)

    def _press(self, event):
        self.dragging = True
        self.x0 = event.x_root
        self.grip.configure(bg=ACCENT)
        self.begin()

    def _move(self, event):
        self.drag((event.x_root - self.x0) / self.S)

    def _release(self, event=None):
        self.dragging = False
        self.grip.configure(bg=TRACK)
        self.end()


class LibItem(ctk.CTkFrame):
    def __init__(self, master, app, path, title, author, pct, thumb, placeholder, title_w):
        super().__init__(master, fg_color="transparent", corner_radius=14)
        self.app = app
        self.path = path
        self.title = title
        self.author = author or "Unknown author"
        self.placeholder = placeholder
        self.selected = False
        self.fit_w = None
        self.columnconfigure(1, weight=1)

        self.thumb_lbl = ctk.CTkLabel(self, text="", image=thumb, width=52, height=52)
        self.thumb_lbl.grid(row=0, column=0, rowspan=3, padx=(10, 10), pady=10)

        self.title_lbl = ctk.CTkLabel(self, text="", text_color=TEXT, anchor="w", font=app.f_item_title)
        self.title_lbl.grid(row=0, column=1, columnspan=2, sticky="w", pady=(11, 0))

        self.author_lbl = ctk.CTkLabel(self, text="", text_color=MUTED, anchor="w", font=app.f_item_sub)
        self.author_lbl.grid(row=1, column=1, sticky="w")
        self.fit(title_w)

        self.pct_lbl = ctk.CTkLabel(self, text=f"{pct}%", text_color=MUTED, anchor="e", font=app.f_item_sub)
        self.pct_lbl.grid(row=1, column=2, sticky="e", padx=(0, 12))

        self.bar = ctk.CTkProgressBar(self, height=4, corner_radius=2, fg_color=TRACK, progress_color=ACCENT)
        self.bar.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(0, 12), pady=(2, 11))
        self.bar.set(pct / 100)

        for w in (self, self.thumb_lbl, self.title_lbl, self.author_lbl, self.pct_lbl, self.bar):
            w.bind("<Button-1>", self._click)

    def _click(self, event=None):
        self.app.on_item_click(self.path)

    def fit(self, title_w):
        """Truncates the title and author to the given logical width, using the full text each time."""
        if title_w == self.fit_w:
            return
        self.fit_w = title_w
        S = self.app.S
        self.title_lbl.configure(text=fit_text(self.title, self.app.tk_item_title, int(title_w * S)))
        self.author_lbl.configure(
            text=fit_text(self.author, self.app.tk_item_sub, int(max(title_w - 68, 40) * S)))

    def set_selected(self, on):
        self.selected = on
        self.configure(fg_color=PANEL2 if on else "transparent")
        self.title_lbl.configure(text_color=ACCENT_TEXT if on else TEXT)

    def recolor(self, placeholder_thumb_img):
        if self.placeholder:
            self.thumb_lbl.configure(image=placeholder_thumb_img)
        self.set_selected(self.selected)
        self.author_lbl.configure(text_color=MUTED)
        self.pct_lbl.configure(text_color=MUTED)
        self.bar.configure(fg_color=TRACK, progress_color=ACCENT)

    def update_pct(self, pct):
        self.pct_lbl.configure(text=f"{pct}%")
        self.bar.set(pct / 100)


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app.root, fg_color=PANEL)
        self.app = app
        self.title("Settings")
        self.resizable(False, False)
        self.transient(app.root)
        self.themed = [(self, {"fg_color": "PANEL"})]
        self.swatches = []
        self.build()
        self.refresh()

        w = 360
        self.update_idletasks()
        h = int(self.winfo_reqheight() / app.S)
        x = app.root.winfo_rootx() + max((app.root.winfo_width() - int(w * app.S)) // 2, 0)
        y = app.root.winfo_rooty() + int(120 * app.S)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(250, self.set_icon)  # CTkToplevel replaces the window icon shortly after creation
        self.after(60, self.focus_force)

    def set_icon(self):
        try:
            if ICO_PATH.exists():
                self.iconbitmap(str(ICO_PATH))
        except Exception:
            pass

    def reg(self, widget, **opts):
        self.themed.append((widget, opts))
        return widget

    def build(self):
        app = self.app
        pad = 24
        self.reg(ctk.CTkLabel(self, text="Appearance", font=app.f_btn, anchor="w"),
                 text_color="MUTED").pack(fill="x", padx=pad, pady=(22, 8))
        self.mode = self.reg(
            ctk.CTkSegmentedButton(self, values=["Dark", "Light"], command=self.on_mode, height=36,
                                   corner_radius=14, font=app.f_btn),
            **app.segment_opts())
        self.mode.pack(fill="x", padx=pad)

        self.reg(ctk.CTkLabel(self, text="Accent colour", font=app.f_btn, anchor="w"),
                 text_color="MUTED").pack(fill="x", padx=pad, pady=(22, 8))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=pad - 3)
        for _name, color in ACCENT_PRESETS:
            b = ctk.CTkButton(row, text="", width=32, height=32, corner_radius=16, fg_color=color,
                              hover_color=mix(color, "#ffffff", 0.2), border_width=0,
                              command=lambda c=color: app.set_accent(c))
            b.pack(side="left", padx=3)
            self.swatches.append((b, color))

        self.custom_btn = self.reg(
            ctk.CTkButton(self, text="Custom colour...", command=self.on_custom, height=34, corner_radius=17,
                          font=app.f_small),
            fg_color="PANEL2", hover_color="PANEL3", text_color="TEXT")
        self.custom_btn.pack(fill="x", padx=pad, pady=(14, 0))

        self.reg(ctk.CTkButton(self, text="Done", command=self.close, height=36, corner_radius=18,
                               font=app.f_btn),
                 fg_color="ACCENT", hover_color="ACCENT_HOVER", text_color="ON_ACCENT"
                 ).pack(fill="x", padx=pad, pady=(24, 22))

    def refresh(self):
        for w, opts in self.themed:
            apply_opts(w, opts)
        self.mode.set("Light" if self.app.theme == "light" else "Dark")
        self.app.style_segment(self.mode)
        accent = self.app.accent
        for b, color in self.swatches:
            on = color == accent
            b.configure(border_width=3 if on else 0, border_color=TEXT)
        custom = accent not in [c for _n, c in ACCENT_PRESETS]
        self.custom_btn.configure(border_width=3 if custom else 0, border_color=TEXT)
        if custom:
            self.custom_btn.configure(fg_color=accent, hover_color=mix(accent, "#ffffff", 0.15),
                                      text_color=ON_ACCENT, text=f"Custom colour  {accent}")
        else:
            self.custom_btn.configure(text="Custom colour...")

    def on_mode(self, value):
        self.app.set_theme(value.lower())

    def on_custom(self):
        res = colorchooser.askcolor(color=self.app.accent, parent=self, title="Choose accent colour")
        if res and res[1]:
            self.app.set_accent(res[1])

    def close(self):
        self.app.settings = None
        self.destroy()


class App:
    def __init__(self, root, store):
        self.root = root
        self.S = get_scale(root)
        self.store = store
        self.theme, self.accent = load_look(store)
        set_palette(self.theme, self.accent)
        self.themed = []
        self.icon_widgets = []
        self.settings = None
        self.instance = vlc.Instance("--no-video")
        self.player = self.instance.media_player_new()

        self.book = None
        self.meta = None
        self.duration_ms = 0
        self.chapters = []
        self.starts = []
        self.cur_chapter = -1
        self.pos_ms = 0
        self.speed = 1.0
        self.loaded = False
        self.ready = False
        self.load_time = 0.0
        self.start_ms = 0
        self.hold_until = 0.0
        self.vlc_chap_tries = 0
        self.vlc_chap_next = 0.0
        self.last_save = 0.0
        self.cover_img = None
        self.err_count = 0
        self.items = {}
        self.seek_dragging = False
        self.shown_playing = None
        self.seek_mode = self.store.get_setting("seek_mode", "chapter")
        self.seek_bounds = (0, 0)
        self.hover_row = ""
        self.drag_start = 0
        self.refit_job = None
        self.lib_w = self.saved_width("lib_width", LIB_DEFAULT, LIB_MIN, LIB_MAX)
        self.panel_w = self.saved_width("panel_width", PANEL_DEFAULT, PANEL_MIN, PANEL_MAX)
        self.lib_applied = self.lib_w
        self.panel_applied = self.panel_w
        self.tooltip = Tooltip(root, self.S)
        self.volume = int(self.store.get_setting("volume", "80"))

        self.make_fonts()
        self.build_ui()
        self.apply_theme()
        self.clear_book()
        self.load_library()
        self.player.audio_set_volume(self.volume)
        self.vol.set(self.volume)

        last = self.store.get_setting("last_book")
        if last and last in self.items:
            self.select_book(last)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.bind("<Configure>", self.on_root_configure, add="+")
        self.root.bind("<space>", lambda e: self.toggle_play())
        self.root.bind("<Left>", lambda e: self.skip(-30))
        self.root.bind("<Right>", lambda e: self.skip(30))
        self.tick()

    # ---------- UI ----------
    def make_fonts(self):
        self.f_heading = ctk.CTkFont(family=FONT, size=20, weight="bold")
        self.f_item_title = ctk.CTkFont(family=FONT, size=13, weight="bold")
        self.f_item_sub = ctk.CTkFont(family=FONT, size=11)
        self.f_author = ctk.CTkFont(family=FONT, size=15)
        self.f_meta = ctk.CTkFont(family=FONT, size=12)
        self.f_time = ctk.CTkFont(family=FONT, size=12)
        self.f_btn = ctk.CTkFont(family=FONT, size=13, weight="bold")
        self.f_speed = ctk.CTkFont(family=FONT, size=14, weight="bold")
        self.f_small = ctk.CTkFont(family=FONT, size=12)
        self.tk_item_title = tkfont.Font(family=FONT, size=-int(13 * self.S), weight="bold")
        self.tk_item_sub = tkfont.Font(family=FONT, size=-int(11 * self.S))
        self.px_title = (FONT, -int(round(22 * self.S)), "bold")
        self.px_chapter = (FONT, -int(round(14 * self.S)), "bold")
        self.px_detail = (FONT, -int(round(14 * self.S)))

    def saved_width(self, key, default, lo, hi):
        try:
            return min(max(int(self.store.get_setting(key, str(default))), lo), hi)
        except ValueError:
            return default

    def setup_tree_style(self):
        S = self.S
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                    rowheight=int(36 * S), borderwidth=0, font=(FONT, -int(round(14 * S))))
        s.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        s.map("Treeview", background=[("selected", ACCENT_DEEP)], foreground=[("selected", SEL_TEXT)])
        s.configure("Treeview.Heading", background=PANEL, foreground=MUTED, relief="flat",
                    borderwidth=0, font=(FONT, -int(round(12 * S)), "bold"), padding=(int(6 * S), int(8 * S)))
        s.map("Treeview.Heading", background=[("active", PANEL)])

    def reg(self, widget, **opts):
        """Records which palette colours a widget uses so apply_theme can recolour it later."""
        self.themed.append((widget, opts))
        return widget

    def reg_icon(self, widget, kind, size):
        self.icon_widgets.append((widget, kind, size))
        return widget

    def segment_opts(self):
        return dict(fg_color="PANEL2", selected_color="ACCENT", selected_hover_color="ACCENT_HOVER",
                    unselected_color="PANEL2", unselected_hover_color="PANEL3", text_color="TEXT")

    def style_segment(self, seg):
        """Text on the selected segment uses the on-accent colour, the others the normal text colour.

        customtkinter does not refresh the inner buttons' background when the theme changes, which leaves
        hairline seams between the segments, so that is reset here too."""
        try:
            cur = seg.get()
            track = seg.cget("fg_color")
            for value, button in seg._buttons_dict.items():
                button.configure(text_color=ON_ACCENT if value == cur else TEXT, bg_color=track)
        except Exception:
            pass

    def btn(self, parent, text, cmd, w, h, accent=False, image=None, font=None):
        b = ctk.CTkButton(
            parent, text=text, image=image, command=cmd, width=w, height=h, corner_radius=h // 2,
            fg_color=ACCENT if accent else PANEL2, hover_color=ACCENT_HOVER if accent else PANEL3,
            text_color=ON_ACCENT if accent else TEXT, font=font or self.f_btn)
        return self.reg(b, fg_color="ACCENT" if accent else "PANEL2",
                        hover_color="ACCENT_HOVER" if accent else "PANEL3",
                        text_color="ON_ACCENT" if accent else "TEXT")

    def make_icons(self):
        self.icon_play = make_icon("play", 30, ON_ACCENT)
        self.icon_pause = make_icon("pause", 30, ON_ACCENT)
        self.icon_prev = make_icon("prev", 20, TEXT)
        self.icon_next = make_icon("next", 20, TEXT)
        self.icon_vol = make_icon("volume", 20, TEXT)
        self.icon_gear = make_icon("gear", 20, TEXT)

    def build_ui(self):
        r = self.root
        r.title("Audiobook Player")
        r.geometry("1200x780")
        r.minsize(1020, 700)
        r.configure(fg_color=BG)
        self.setup_tree_style()
        r.grid_columnconfigure(2, weight=1)
        r.grid_rowconfigure(0, weight=1)
        self.make_icons()

        # ----- library sidebar -----
        side = self.reg(ctk.CTkFrame(r, width=self.lib_w, corner_radius=20, fg_color=PANEL), fg_color="PANEL")
        self.side = side
        side.grid(row=0, column=0, sticky="ns", padx=(14, 0), pady=(14, 7))
        side.pack_propagate(False)
        head = ctk.CTkFrame(side, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(16, 8))
        self.reg(ctk.CTkLabel(head, text="Library", text_color=TEXT, font=self.f_heading),
                 text_color="TEXT").pack(side="left")
        self.btn(head, "+ Add books", self.add_books, 108, 34, accent=True).pack(side="right")
        gear = self.btn(head, "", self.open_settings, 34, 34, image=self.icon_gear)
        self.reg_icon(gear, "gear", 20).pack(side="right", padx=(0, 8))

        self.lib_list = self.reg(
            ctk.CTkScrollableFrame(side, fg_color=PANEL, scrollbar_button_color=TRACK,
                                   scrollbar_button_hover_color=MUTED),
            fg_color="PANEL", scrollbar_button_color="TRACK", scrollbar_button_hover_color="MUTED")
        self.lib_list.pack(fill="both", expand=True, padx=(8, 4), pady=(0, 6))
        self.empty_lbl = self.reg(ctk.CTkLabel(
            self.lib_list, text="No books yet.\nClick + Add books to begin.", text_color=MUTED,
            font=self.f_small, justify="center"), text_color="MUTED")

        foot = ctk.CTkFrame(side, fg_color="transparent")
        foot.pack(fill="x", padx=14, pady=(0, 14))
        self.btn(foot, "Remove current book", self.remove_book, 200, 32, font=self.f_small).pack(anchor="w")

        self.lib_split = Splitter(r, self.S, self.begin_lib_drag, self.drag_lib, self.end_drag)
        self.lib_split.grid(row=0, column=1, sticky="ns", pady=(14, 7))

        # ----- now playing -----
        hero = self.reg(ctk.CTkFrame(r, corner_radius=20, fg_color=PANEL), fg_color="PANEL")
        hero.grid(row=0, column=2, sticky="nsew", padx=0, pady=(14, 7))
        content = ctk.CTkFrame(hero, fg_color="transparent")
        content.place(relx=0.5, rely=0.5, anchor="center")

        self.cover_box = 250
        self.cover_label = ctk.CTkLabel(content, text="", width=self.cover_box, height=self.cover_box)
        self.cover_label.pack(pady=(0, 18))

        wrap = int(310 * self.S)
        self.title_lbl = tk.Label(content, text="", bg=PANEL, fg=TEXT, font=self.px_title,
                                  wraplength=wrap, justify="center")
        self.reg(self.title_lbl, bg="PANEL", fg="TEXT")
        self.title_lbl.pack()
        self.author_lbl = self.reg(ctk.CTkLabel(content, text="", text_color=MUTED, font=self.f_author),
                                   text_color="MUTED")
        self.author_lbl.pack(pady=(6, 0))
        self.meta_lbl = self.reg(ctk.CTkLabel(content, text="", text_color=MUTED, font=self.f_meta),
                                 text_color="MUTED")
        self.meta_lbl.pack(pady=(2, 0))
        self.chapter_lbl = tk.Label(content, text="", bg=PANEL, fg=ACCENT_TEXT, font=self.px_chapter,
                                    wraplength=wrap, justify="center")
        self.reg(self.chapter_lbl, bg="PANEL", fg="ACCENT_TEXT")
        self.chapter_lbl.pack(pady=(16, 0))

        # ----- draggable splitter and chapters/details panel -----
        self.panel_split = Splitter(r, self.S, self.begin_panel_drag, self.drag_panel, self.end_drag)
        self.panel_split.grid(row=0, column=3, sticky="ns", pady=(14, 7))

        self.panel = self.reg(ctk.CTkFrame(r, width=self.panel_w, corner_radius=20, fg_color=PANEL),
                              fg_color="PANEL")
        self.panel.grid(row=0, column=4, sticky="ns", padx=(0, 14), pady=(14, 7))
        self.panel.pack_propagate(False)
        panel = self.panel

        self.tabs = self.reg(ctk.CTkSegmentedButton(
            panel, values=["Chapters", "Details"], command=self.on_tab, height=36, corner_radius=14,
            fg_color=PANEL2, selected_color=ACCENT, selected_hover_color=ACCENT_HOVER,
            unselected_color=PANEL2, unselected_hover_color=PANEL3, text_color=TEXT, font=self.f_btn),
            **self.segment_opts())
        self.tabs.pack(fill="x", padx=16, pady=(16, 10))
        self.tabs.set("Chapters")

        body = ctk.CTkFrame(panel, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=(10, 6), pady=(0, 12))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)

        S = self.S
        self.chap_frame = ctk.CTkFrame(body, fg_color="transparent")
        self.chap_frame.grid(row=0, column=0, sticky="nsew")
        self.chap = ttk.Treeview(self.chap_frame, columns=("n", "title", "start"), show="headings",
                                 selectmode="browse")
        self.chap.heading("n", text="#", anchor="center")
        self.chap.heading("title", text="Chapter", anchor="w")
        self.chap.heading("start", text="Starts at", anchor="e")
        self.chap.column("n", width=int(44 * S), anchor="center", stretch=False)
        self.chap.column("title", width=int(190 * S), anchor="w")
        self.chap.column("start", width=int(80 * S), anchor="e", stretch=False)
        csb = self.reg(ctk.CTkScrollbar(self.chap_frame, command=self.chap.yview, button_color=TRACK,
                                        button_hover_color=MUTED),
                       button_color="TRACK", button_hover_color="MUTED")
        self.chap.configure(yscrollcommand=csb.set)
        self.chap.pack(side="left", fill="both", expand=True)
        csb.pack(side="right", fill="y", padx=(4, 0))
        self.chap.bind("<ButtonRelease-1>", self.on_chapter_click)
        self.chap.bind("<Return>", self.on_chapter_open)
        self.chap.bind("<Motion>", self.on_chap_motion)
        self.chap.bind("<Leave>", self.on_chap_leave)
        self.chap.bind("<ButtonPress-1>", self.on_chap_leave, add="+")
        self.chap.bind("<MouseWheel>", self.on_chap_leave, add="+")

        self.det_frame = ctk.CTkFrame(body, fg_color="transparent")
        self.det_frame.grid(row=0, column=0, sticky="nsew")
        self.det = tk.Text(self.det_frame, bg=PANEL, fg=TEXT, relief="flat", bd=0, wrap="word",
                           padx=int(10 * S), pady=int(6 * S), font=self.px_detail, highlightthickness=0,
                           cursor="arrow")
        self.reg(self.det, bg="PANEL", fg="TEXT")
        dsb = self.reg(ctk.CTkScrollbar(self.det_frame, command=self.det.yview, button_color=TRACK,
                                        button_hover_color=MUTED),
                       button_color="TRACK", button_hover_color="MUTED")
        self.det.configure(yscrollcommand=dsb.set)
        self.det.pack(side="left", fill="both", expand=True)
        dsb.pack(side="right", fill="y", padx=(4, 0))
        self.style_details()
        self.det.config(state="disabled")
        self.det.bind("<ButtonRelease-1>", lambda e: self.root.focus_set())
        self.det_frame.grid_remove()

        # ----- player bar -----
        bar = self.reg(ctk.CTkFrame(r, corner_radius=20, fg_color=PANEL), fg_color="PANEL")
        bar.grid(row=1, column=0, columnspan=5, sticky="ew", padx=14, pady=(7, 14))

        slider_opts = dict(fg_color="TRACK", progress_color="ACCENT", button_color="KNOB",
                           button_hover_color="KNOB_HOVER")

        trow = ctk.CTkFrame(bar, fg_color="transparent")
        trow.pack(fill="x", padx=24, pady=(14, 0))
        self.mode_btn = self.reg(ctk.CTkSegmentedButton(
            trow, values=["Chapter", "Whole book"], command=self.on_mode, height=28, corner_radius=12,
            fg_color=PANEL2, selected_color=ACCENT, selected_hover_color=ACCENT_HOVER,
            unselected_color=PANEL2, unselected_hover_color=PANEL3, text_color=TEXT, font=self.f_small),
            **self.segment_opts())
        self.mode_btn.pack(side="left")
        self.mode_btn.set("Chapter")
        self.book_lbl = self.reg(ctk.CTkLabel(trow, text="", text_color=MUTED, font=self.f_small, anchor="e"),
                                 text_color="MUTED")
        self.book_lbl.pack(side="right")

        srow = ctk.CTkFrame(bar, fg_color="transparent")
        srow.pack(fill="x", padx=24, pady=(6, 2))
        self.elapsed_lbl = self.reg(ctk.CTkLabel(srow, text="0:00:00", text_color=MUTED, font=self.f_time,
                                                 width=64, anchor="w"), text_color="MUTED")
        self.elapsed_lbl.pack(side="left")
        self.seek = self.reg(ctk.CTkSlider(
            srow, from_=0, to=1, height=18, command=self.on_seek_move, fg_color=TRACK,
            progress_color=ACCENT, button_color=KNOB, button_hover_color=KNOB_HOVER), **slider_opts)
        self.seek.set(0)
        self.seek.pack(side="left", fill="x", expand=True, padx=10)
        self.seek.bind("<ButtonPress-1>", self.on_seek_press)
        self.seek.bind("<ButtonRelease-1>", self.on_seek_release)
        self.remain_lbl = self.reg(ctk.CTkLabel(srow, text="-0:00:00", text_color=MUTED, font=self.f_time,
                                                width=72, anchor="e"), text_color="MUTED")
        self.remain_lbl.pack(side="left")

        crow = ctk.CTkFrame(bar, fg_color="transparent")
        crow.pack(fill="x", padx=24, pady=(4, 16))
        crow.columnconfigure(0, weight=1, uniform="c")
        crow.columnconfigure(2, weight=1, uniform="c")
        left = ctk.CTkFrame(crow, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w")
        mid = ctk.CTkFrame(crow, fg_color="transparent")
        mid.grid(row=0, column=1)
        right = ctk.CTkFrame(crow, fg_color="transparent")
        right.grid(row=0, column=2, sticky="e")

        self.reg(ctk.CTkLabel(left, text="Speed", text_color=MUTED, font=self.f_small),
                 text_color="MUTED").pack(side="left", padx=(0, 10))
        pill = self.reg(ctk.CTkFrame(left, fg_color=PANEL2, corner_radius=22), fg_color="PANEL2")
        pill.pack(side="left")

        def speed_btn(sign, delta, pad):
            return self.reg(ctk.CTkButton(
                pill, text=sign, width=36, height=36, corner_radius=18, fg_color="transparent",
                hover_color=PANEL3, text_color=TEXT, font=self.f_speed,
                command=lambda: self.change_speed(delta)),
                hover_color="PANEL3", text_color="TEXT").pack(side="left", padx=pad, pady=5)

        speed_btn("-", -0.1, (5, 0))
        self.speed_lbl = self.reg(ctk.CTkLabel(pill, text="1.0x", width=54, text_color=TEXT, font=self.f_speed),
                                  text_color="TEXT")
        self.speed_lbl.pack(side="left")
        speed_btn("+", 0.1, (0, 5))

        self.reg_icon(self.btn(mid, "", self.prev_chapter, 46, 46, image=self.icon_prev),
                      "prev", 20).pack(side="left", padx=5)
        self.btn(mid, "-30s", lambda: self.skip(-30), 62, 46).pack(side="left", padx=5)
        self.play_btn = self.btn(mid, "", self.toggle_play, 70, 70, accent=True, image=self.icon_play)
        self.play_btn.pack(side="left", padx=12)
        self.btn(mid, "+30s", lambda: self.skip(30), 62, 46).pack(side="left", padx=5)
        self.reg_icon(self.btn(mid, "", self.next_chapter, 46, 46, image=self.icon_next),
                      "next", 20).pack(side="left", padx=5)

        vol_icon = ctk.CTkLabel(right, text="", image=self.icon_vol, width=24)
        self.reg_icon(vol_icon, "volume", 20).pack(side="left", padx=(0, 8))
        self.vol = self.reg(ctk.CTkSlider(
            right, from_=0, to=100, number_of_steps=100, width=130, height=16, command=self.on_volume,
            fg_color=TRACK, progress_color=ACCENT, button_color=KNOB, button_hover_color=KNOB_HOVER),
            **slider_opts)
        self.vol.pack(side="left")
        self.vol.bind("<ButtonRelease-1>", self.on_volume_done)

    def style_details(self):
        S = self.S
        d = self.det
        d.tag_configure("h", foreground=ACCENT_TEXT, font=(FONT, -int(round(13 * S)), "bold"),
                        spacing1=int(8 * S), spacing3=int(6 * S))
        d.tag_configure("k", foreground=MUTED, font=(FONT, -int(round(12 * S)), "bold"),
                        spacing1=int(12 * S))
        d.tag_configure("raw", foreground=RAW, font=("Consolas", -int(round(12 * S))))
        d.tag_configure("v", foreground=TEXT, font=self.px_detail)

    # ---------- theme ----------
    def apply_theme(self):
        ctk.set_appearance_mode(self.theme)  # also switches the Windows title bar
        self.root.configure(fg_color=BG)
        self.setup_tree_style()
        for widget, opts in self.themed:
            apply_opts(widget, opts)
        self.lib_split.recolor()
        self.panel_split.recolor()
        self.style_details()
        self.make_icons()
        for widget, kind, size in self.icon_widgets:
            widget.configure(image=make_icon(kind, size, TEXT))
        self.style_segment(self.tabs)
        self.style_segment(self.mode_btn)
        ph = placeholder_thumb()
        for item in self.items.values():
            item.recolor(ph)
        self.set_cover(self.meta["cover"] if self.meta else None)
        self.shown_playing = None
        self.refresh_ui()
        if self.settings is not None:
            self.settings.refresh()
            # switching the Windows title bar colour hides and re-shows both windows, and the dialog
            # (a transient of the main window) comes back hidden
            self.root.after(40, self.raise_settings)

    def raise_settings(self):
        if self.settings is not None:
            try:
                self.settings.deiconify()
                self.settings.lift()
                self.settings.focus_force()
            except Exception:
                pass

    def set_theme(self, mode):
        if mode == self.theme:
            return
        self.theme = mode
        self.store.set_setting("theme", mode)
        set_palette(self.theme, self.accent)
        self.apply_theme()

    def set_accent(self, color):
        color = valid_hex(color, self.accent)
        if color == self.accent:
            return
        self.accent = color
        self.store.set_setting("accent", color)
        set_palette(self.theme, self.accent)
        self.apply_theme()

    def open_settings(self):
        if self.settings is not None:
            self.raise_settings()
            return
        self.settings = SettingsDialog(self)

    def on_tab(self, value):
        if value == "Details":
            self.chap_frame.grid_remove()
            self.det_frame.grid()
        else:
            self.det_frame.grid_remove()
            self.chap_frame.grid()
        self.style_segment(self.tabs)

    # ---------- resizable library and chapter panels ----------
    def room_for_sides(self):
        """Logical width the library and chapter panels may share, keeping the middle at HERO_MIN."""
        total = self.root.winfo_width() / self.S
        split = max(int(10 * self.S), 6) / self.S
        return total - (14 + 14 + 2 * split) - HERO_MIN

    def fit_widths(self, lib, panel):
        lib = min(max(lib, LIB_MIN), LIB_MAX)
        panel = min(max(panel, PANEL_MIN), PANEL_MAX)
        over = lib + panel - self.room_for_sides()
        if over > 0:
            # window too small for both: give back the same fraction of each panel's width above its minimum
            spare = (lib - LIB_MIN) + (panel - PANEL_MIN)
            keep = max(spare - over, 0) / spare if spare else 0
            lib = LIB_MIN + (lib - LIB_MIN) * keep
            panel = PANEL_MIN + (panel - PANEL_MIN) * keep
        return int(lib), int(panel)

    def apply_widths(self):
        if self.root.winfo_width() < 300:
            return
        lib, panel = self.fit_widths(self.lib_w, self.panel_w)
        if lib != self.lib_applied:
            self.lib_applied = lib
            self.side.configure(width=lib)
            self.schedule_refit()
        if panel != self.panel_applied:
            self.panel_applied = panel
            self.panel.configure(width=panel)

    def on_root_configure(self, event):
        if event.widget is self.root:
            self.apply_widths()

    def begin_drag(self):
        # keep what is on screen as the baseline so the other panel never moves while dragging
        self.lib_w, self.panel_w = self.lib_applied, self.panel_applied
        self.tooltip.hide()

    def begin_lib_drag(self):
        self.begin_drag()
        self.drag_start = self.lib_w

    def drag_lib(self, delta):
        hi = max(min(LIB_MAX, self.room_for_sides() - self.panel_w), LIB_MIN)
        self.lib_w = int(min(max(self.drag_start + delta, LIB_MIN), hi))
        self.apply_widths()

    def begin_panel_drag(self):
        self.begin_drag()
        self.drag_start = self.panel_w

    def drag_panel(self, delta):
        hi = max(min(PANEL_MAX, self.room_for_sides() - self.lib_w), PANEL_MIN)
        self.panel_w = int(min(max(self.drag_start - delta, PANEL_MIN), hi))
        self.apply_widths()

    def end_drag(self):
        self.store.set_setting("lib_width", str(self.lib_w))
        self.store.set_setting("panel_width", str(self.panel_w))

    def lib_text_width(self):
        return max(self.lib_applied - 134, 80)

    def schedule_refit(self):
        if self.refit_job is None:
            self.refit_job = self.root.after(30, self.refit_items)

    def refit_items(self):
        self.refit_job = None
        w = self.lib_text_width()
        for item in self.items.values():
            item.fit(w)

    def on_chap_motion(self, event):
        row = self.chap.identify_row(event.y)
        if row == self.hover_row:
            return
        self.hover_row = row
        self.tooltip.hide()
        if row and row.isdigit() and int(row) < len(self.chapters):
            self.tooltip.schedule(self.chapters[int(row)][1], event.x_root + 16, event.y_root + 22)

    def on_chap_leave(self, event=None):
        self.hover_row = ""
        self.tooltip.hide()

    # ---------- library ----------
    def update_empty(self):
        if self.items:
            self.empty_lbl.pack_forget()
        else:
            self.empty_lbl.pack(pady=40)

    def add_item(self, path, title, author, pct):
        thumb, placeholder = list_thumb(path)
        item = LibItem(self.lib_list, self, path, title, author, pct, thumb, placeholder,
                       self.lib_text_width())
        item.pack(fill="x", pady=3, padx=2)
        self.items[path] = item
        self.update_empty()

    def load_library(self):
        for r in self.store.all():
            self.add_item(r["path"], r["title"], r["author"], percent(r["position_ms"], r["duration_ms"]))
        self.update_empty()

    def add_books(self):
        paths = filedialog.askopenfilenames(
            title="Choose audiobooks",
            filetypes=[("Audiobooks", "*.m4b *.m4a *.mp4"), ("All files", "*.*")],
        )
        first = None
        for p in paths:
            p = os.path.normpath(p)
            if p in self.items:
                continue
            m = read_meta(p)
            self.store.add(p, m["title"], m["author"], m["duration_ms"])
            self.add_item(p, m["title"], m["author"], 0)
            if first is None:
                first = p
        if first and not self.book:
            self.select_book(first)

    def remove_book(self):
        if not self.book:
            return
        path = self.book
        if not messagebox.askyesno(
            "Remove book",
            "Remove this book from the library?\nYour file is not deleted, "
            "but your saved progress for it will be.",
        ):
            return
        self.player.stop()
        self.loaded = False
        self.ready = False
        self.clear_book()
        self.store.remove(path)
        item = self.items.pop(path, None)
        if item:
            item.destroy()
        self.update_empty()

    def on_item_click(self, path):
        if path == self.book:
            if not self.is_playing():
                self.toggle_play()
            return
        self.select_book(path, autoplay=True)

    def highlight(self, path):
        for p, item in self.items.items():
            item.set_selected(p == path)

    # ---------- book display ----------
    def set_cover(self, data):
        img = cover_image(data, self.cover_box, 18)
        self.cover_label.configure(image=img)
        self.cover_img = img

    def clear_book(self):
        self.book = None
        self.meta = None
        self.chapters = []
        self.starts = []
        self.duration_ms = 0
        self.pos_ms = 0
        self.cur_chapter = -1
        self.title_lbl.config(text="No book selected")
        self.author_lbl.configure(text="Click + Add books to begin")
        self.meta_lbl.configure(text="")
        self.chapter_lbl.config(text="")
        self.set_cover(None)
        self.chap.delete(*self.chap.get_children())
        self.det.config(state="normal")
        self.det.delete("1.0", "end")
        self.det.config(state="disabled")
        self.elapsed_lbl.configure(text="0:00:00")
        self.remain_lbl.configure(text="-0:00:00")
        self.book_lbl.configure(text="")
        self.seek_bounds = (0, 0)
        self.seek.set(0)
        self.speed_lbl.configure(text="1.0x")
        self.highlight(None)
        self.update_mode_ui()
        self.root.title("Audiobook Player")

    def update_meta_line(self):
        bits = []
        if self.meta and self.meta["year"]:
            bits.append(self.meta["year"])
        if self.duration_ms:
            bits.append(fmt_time(self.duration_ms))
        if self.chapters:
            bits.append(f"{len(self.chapters)} chapters")
        self.meta_lbl.configure(text="   |   ".join(bits))

    def fill_chapters(self):
        self.tooltip.hide()
        self.hover_row = ""
        self.chap.delete(*self.chap.get_children())
        self.starts = [c[0] for c in self.chapters]
        if self.chapters:
            for i, (start, title) in enumerate(self.chapters):
                self.chap.insert("", "end", iid=str(i), values=(i + 1, title, fmt_time(start)))
        else:
            self.chap.insert("", "end", iid="none", values=("", "No chapters found in this file", ""))
        self.cur_chapter = -1
        self.update_meta_line()
        self.update_mode_ui()

    def fill_details(self):
        if not self.meta:
            return
        t = self.det
        t.config(state="normal")
        t.delete("1.0", "end")

        def section(name):
            t.insert("end", name + "\n", "h")

        def entry(label, value, raw=None):
            t.insert("end", label, "k")
            if raw:
                t.insert("end", "   " + raw, "raw")
            t.insert("end", "\n" + (value if value else "-") + "\n", "v")

        section("TAGS")
        if self.meta["tags"]:
            for label, value, raw in self.meta["tags"]:
                entry(label, value, raw)
        else:
            t.insert("end", "No tags found\n", "v")
        t.insert("end", "\n")
        section("FILE AND AUDIO")
        for label, value in self.meta["tech"]:
            entry(label, value)
        entry("Chapter source", self.meta["chapter_source"])
        if self.meta["scan"] and not self.chapters:
            entry("Track layout (for troubleshooting)", "\n".join(self.meta["scan"]))
        t.config(state="disabled")

    def show_book(self):
        m = self.meta
        self.title_lbl.config(text=m["title"])
        self.author_lbl.configure(text=m["author"] or "Unknown author")
        self.set_cover(m["cover"])
        self.fill_details()
        self.fill_chapters()
        self.speed_lbl.configure(text=f"{self.speed:.1f}x")
        self.root.title(f"{m['title']} - Audiobook Player")
        self.refresh_ui()

    # ---------- book selection and playback ----------
    def select_book(self, path, autoplay=False):
        if not os.path.exists(path):
            messagebox.showerror("File not found", f"Cannot find:\n{path}")
            return
        if self.book:
            self.save_progress()
        self.player.stop()
        self.loaded = False
        self.ready = False
        self.meta = read_meta(path)
        row = self.store.get(path)
        self.book = path
        self.duration_ms = self.meta["duration_ms"] or (row["duration_ms"] if row else 0)
        self.pos_ms = row["position_ms"] if row else 0
        self.speed = row["speed"] if row and row["speed"] else 1.0
        self.chapters = list(self.meta["chapters"])
        self.vlc_chap_tries = 99 if self.chapters else 0
        self.vlc_chap_next = 0.0
        self.store.set_setting("last_book", path)
        self.highlight(path)
        self.show_book()
        if autoplay:
            self.toggle_play()

    def is_playing(self):
        if not self.loaded:
            return False
        return self.player.get_state() in (vlc.State.Opening, vlc.State.Buffering, vlc.State.Playing)

    def ensure_loaded(self):
        if self.duration_ms > 0 and self.pos_ms >= self.duration_ms - 1500:
            self.pos_ms = 0
        media = self.instance.media_new(self.book)
        media.add_option(f":start-time={self.pos_ms / 1000:.3f}")
        self.player.set_media(media)
        self.player.audio_set_volume(self.volume)
        self.start_ms = self.pos_ms
        self.loaded = True
        self.ready = False
        self.load_time = time.time()
        self.player.play()

    def toggle_play(self):
        if not self.book:
            return
        if not self.loaded:
            self.ensure_loaded()
            return
        if self.is_playing():
            self.player.set_pause(1)
            self.save_progress()
        else:
            self.player.play()

    def seek_to(self, ms):
        if not self.book:
            return
        if self.duration_ms:
            ms = min(max(ms, 0), max(self.duration_ms - 500, 0))
        else:
            ms = max(ms, 0)
        ms = int(ms)
        self.pos_ms = ms
        self.hold_until = time.time() + 0.7
        if self.loaded:
            if not self.ready:
                self.start_ms = ms
                self.load_time = time.time()
            self.player.set_time(ms)
        self.refresh_ui()

    def skip(self, seconds):
        self.seek_to(self.pos_ms + seconds * 1000)

    def chapter_index(self, ms):
        if not self.starts:
            return -1
        return max(bisect_right(self.starts, ms + 250) - 1, 0)

    def prev_chapter(self):
        if not self.book:
            return
        if not self.starts:
            self.seek_to(0)
            return
        i = self.chapter_index(self.pos_ms)
        if i == 0 or self.pos_ms - self.starts[i] > 3000:
            self.seek_to(self.starts[i])
        else:
            self.seek_to(self.starts[i - 1])

    def next_chapter(self):
        if not self.starts:
            return
        i = self.chapter_index(self.pos_ms)
        if i + 1 < len(self.starts):
            self.seek_to(self.starts[i + 1])

    def change_speed(self, delta):
        if not self.book:
            return
        self.speed = round(min(3.0, max(0.5, self.speed + delta)), 1)
        self.speed_lbl.configure(text=f"{self.speed:.1f}x")
        if self.loaded:
            self.player.set_rate(self.speed)
        self.save_progress()

    def jump_to_chapter(self, iid):
        if not iid or not iid.isdigit():
            return
        idx = int(iid)
        if idx >= len(self.starts):
            return
        self.seek_to(self.starts[idx])
        if not self.is_playing():
            self.toggle_play()
        self.root.focus_set()

    def on_chapter_click(self, event):
        iid = self.chap.identify_row(event.y)
        self.jump_to_chapter(iid)

    def on_chapter_open(self, event=None):
        sel = self.chap.selection()
        if sel:
            self.jump_to_chapter(sel[0])

    def on_seek_press(self, event=None):
        self.seek_dragging = True

    def effective_mode(self):
        return "chapter" if (self.seek_mode == "chapter" and self.chapters) else "book"

    def compute_bounds(self):
        dur = self.duration_ms
        if self.effective_mode() == "chapter" and self.starts:
            idx = self.chapter_index(self.pos_ms)
            start = self.starts[idx]
            end = self.starts[idx + 1] if idx + 1 < len(self.starts) else dur
            if end <= start:
                end = max(dur, start + 1)
            return start, end - start
        return 0, dur

    def update_mode_ui(self):
        if self.chapters:
            self.mode_btn.configure(state="normal")
            self.mode_btn.set("Chapter" if self.seek_mode == "chapter" else "Whole book")
        else:
            self.mode_btn.set("Whole book")
            self.mode_btn.configure(state="disabled")
        self.style_segment(self.mode_btn)

    def on_mode(self, value):
        self.seek_mode = "chapter" if value == "Chapter" else "book"
        self.store.set_setting("seek_mode", self.seek_mode)
        self.style_segment(self.mode_btn)
        self.refresh_ui()
        self.root.focus_set()

    def update_time_labels(self, pos):
        dur = self.duration_ms
        start, span = self.seek_bounds
        if self.effective_mode() == "chapter":
            el = min(max(pos - start, 0), span)
            self.elapsed_lbl.configure(text=fmt_time(el))
            self.remain_lbl.configure(text="-" + fmt_time(span - el))
            self.book_lbl.configure(text="Book remaining  -" + fmt_time(max(dur - pos, 0)))
        else:
            self.elapsed_lbl.configure(text=fmt_time(pos))
            self.remain_lbl.configure(text="-" + fmt_time(max(dur - pos, 0)))
            self.book_lbl.configure(text="")

    def on_seek_move(self, frac):
        start, span = self.seek_bounds
        if span > 0:
            self.update_time_labels(start + frac * span)

    def on_seek_release(self, event=None):
        start, span = self.seek_bounds
        frac = self.seek.get()
        self.seek_dragging = False
        if span > 0:
            self.seek_to(start + frac * span)
        self.root.focus_set()

    def on_volume(self, value):
        self.volume = int(value)
        self.player.audio_set_volume(self.volume)

    def on_volume_done(self, event=None):
        self.store.set_setting("volume", str(self.volume))
        self.root.focus_set()

    # ---------- progress ----------
    def save_progress(self):
        if not self.book:
            return
        if self.loaded and not self.ready:
            return
        self.store.save_progress(self.book, self.pos_ms, self.speed, self.duration_ms)
        item = self.items.get(self.book)
        if item:
            item.update_pct(percent(self.pos_ms, self.duration_ms))
        self.last_save = time.time()

    def try_vlc_chapters(self):
        self.vlc_chap_tries += 1
        self.vlc_chap_next = time.time() + 1.5
        try:
            descs = self.player.get_full_chapter_descriptions(-1)
        except Exception:
            return
        if not descs:
            return
        found = []
        for i, d in enumerate(descs, 1):
            try:
                if isinstance(d, dict):
                    start = d.get("time_offset")
                    name = d.get("name")
                else:
                    start = getattr(d, "time_offset", None)
                    name = getattr(d, "name", None) or getattr(d, "psz_name", None)
                if start is None:
                    continue
                if isinstance(name, bytes):
                    name = name.decode("utf-8", "replace")
                found.append((int(start), name or f"Chapter {i}"))
            except Exception:
                pass
        if found:
            found.sort(key=lambda c: c[0])
            self.chapters = found
            self.vlc_chap_tries = 99
            if self.meta:
                self.meta["chapter_source"] = "VLC"
            self.fill_chapters()
            self.fill_details()

    def update_player_state(self):
        if self.book and self.loaded:
            state = self.player.get_state()
            if state == vlc.State.Ended:
                self.pos_ms = self.duration_ms
                self.player.stop()
                self.loaded = False
                self.ready = False
                self.save_progress()
            elif state == vlc.State.Error:
                self.player.stop()
                self.loaded = False
                self.ready = False
                messagebox.showerror("Playback error", "VLC could not play this file.")
            else:
                if self.duration_ms <= 0:
                    length = self.player.get_length()
                    if length > 0:
                        self.duration_ms = length
                        self.update_meta_line()
                if state == vlc.State.Playing:
                    if abs(self.player.get_rate() - self.speed) > 0.01:
                        self.player.set_rate(self.speed)
                    t = self.player.get_time()
                    if not self.ready:
                        if t >= 0 and t >= self.start_ms - 1500:
                            self.ready = True
                        elif time.time() - self.load_time > 3:
                            self.player.set_time(self.start_ms)
                            self.load_time = time.time()
                    if self.ready and t >= 0 and time.time() >= self.hold_until:
                        self.pos_ms = t
                elif state == vlc.State.Paused and self.ready:
                    t = self.player.get_time()
                    if t >= 0 and time.time() >= self.hold_until:
                        self.pos_ms = t
                if (self.ready and state == vlc.State.Playing and self.vlc_chap_tries < 6
                        and time.time() >= self.vlc_chap_next):
                    self.try_vlc_chapters()
                if self.ready and time.time() - self.last_save > 5:
                    self.save_progress()
        self.refresh_ui()

    def refresh_ui(self):
        playing = self.is_playing()
        if playing != self.shown_playing:
            self.play_btn.configure(image=self.icon_pause if playing else self.icon_play)
            self.shown_playing = playing
        if not self.book:
            return
        if not self.seek_dragging:
            self.seek_bounds = self.compute_bounds()
            start, span = self.seek_bounds
            frac = (self.pos_ms - start) / span if span > 0 else 0
            self.seek.set(min(max(frac, 0), 1))
            self.update_time_labels(self.pos_ms)
        if self.chapters:
            idx = self.chapter_index(self.pos_ms)
            if idx != self.cur_chapter:
                if self.chap.exists(str(idx)):
                    self.chap.selection_set(str(idx))
                    self.chap.see(str(idx))
                self.cur_chapter = idx
                name = self.chapters[idx][1]
                if name.lower().startswith("chapter"):
                    self.chapter_lbl.config(text=name)
                else:
                    self.chapter_lbl.config(text=f"Chapter {idx + 1}: {name}")
        else:
            self.chapter_lbl.config(text="")

    def tick(self):
        try:
            self.update_player_state()
        except Exception:
            self.err_count += 1
            if self.err_count <= 20:
                log_error()
        self.root.after(250, self.tick)

    def on_close(self):
        try:
            self.save_progress()
        except Exception:
            pass
        try:
            self.player.stop()
            self.player.release()
            self.instance.release()
        except Exception:
            pass
        self.root.destroy()


def main():
    store = Store()
    ctk.set_appearance_mode(load_look(store)[0])
    root = ctk.CTk()
    ico = ensure_icon()
    if ico:
        try:
            root.iconbitmap(ico)
        except Exception:
            pass
    App(root, store)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log_error()
        try:
            messagebox.showerror("Audiobook Player crashed", f"Details were saved to:\n{LOG_PATH}")
        except Exception:
            pass