import subprocess
import sys
import time
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

APP_DIR = Path.home() / ".m4b_player"
ICO_PATH = APP_DIR / "audiobook.ico"
LOG_PATH = APP_DIR / "make_icon.log"
SCRIPT_DIR = Path(__file__).resolve().parent
SHORTCUT_NAME = "Audiobook Player.lnk"


def log(msg):
    line = time.strftime("%H:%M:%S") + "  " + str(msg)
    try:
        print(line)
    except Exception:
        pass
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def show(kind, title, text):
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.update()
        try:
            if kind == "info":
                messagebox.showinfo(title, text, parent=root)
            else:
                messagebox.showerror(title, text, parent=root)
        finally:
            root.destroy()
    except Exception:
        log("Could not show message box: " + traceback.format_exc())


def draw_icon(size=512):
    from PIL import Image, ImageDraw

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


def save_ico(path):
    img = draw_icon(512)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="ICO",
             sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def find_app_file():
    f = SCRIPT_DIR / "audiobook.pyw"
    if f.exists():
        return f
    # the app file may have been renamed: accept it if it is the only other .pyw next to this script
    try:
        others = [p for p in SCRIPT_DIR.glob("*.pyw") if p.name.lower() != "make_icon.pyw"]
    except Exception:
        others = []
    return others[0] if len(others) == 1 else None


def ps_quote(text):
    return "'" + str(text).replace("'", "''") + "'"


def make_shortcut(app_file, ico_file):
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    target = pythonw if pythonw.exists() else Path(sys.executable)
    args = '"' + str(app_file) + '"'
    parts = [
        # report the shortcut path as UTF-8 so folders with accented or non-Latin names still work
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8",
        "$desktop = [Environment]::GetFolderPath('Desktop')",
        "$lnk = Join-Path $desktop " + ps_quote(SHORTCUT_NAME),
        "$sh = New-Object -ComObject WScript.Shell",
        "$s = $sh.CreateShortcut($lnk)",
        "$s.TargetPath = " + ps_quote(target),
        "$s.Arguments = " + ps_quote(args),
        "$s.WorkingDirectory = " + ps_quote(app_file.parent),
        "$s.IconLocation = " + ps_quote(str(ico_file) + ",0"),
        "$s.Description = 'Audiobook Player'",
        "$s.Save()",
        "Write-Output $lnk",
    ]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    log(f"Shortcut target: {target}")
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "; ".join(parts)],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=flags, timeout=60)
    log(f"PowerShell exit code: {result.returncode}")
    if result.stderr.strip():
        log("PowerShell stderr: " + result.stderr.strip())
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "PowerShell could not create the shortcut.")
    lnk = result.stdout.strip()
    if not lnk or not Path(lnk).exists():
        raise RuntimeError(f"PowerShell finished but the shortcut file was not found: {lnk}")
    return lnk


def main():
    log("make_icon started. Python: " + sys.executable)
    try:
        if not sys.platform.startswith("win"):
            raise RuntimeError("This tool creates a Windows desktop shortcut, so it only works on Windows.")
        app_file = find_app_file()
        log(f"App file: {app_file}")
        if app_file is None:
            raise FileNotFoundError(
                "Could not find audiobook.pyw.\nLooked in:\n"
                f"{SCRIPT_DIR}\n\n"
                "Put make_icon.pyw in the same folder as audiobook.pyw and run it again.")
        save_ico(ICO_PATH)
        log(f"Icon saved: {ICO_PATH}")
        lnk = make_shortcut(app_file, ICO_PATH)
        log(f"Shortcut created: {lnk}")
        show("info", "Done",
             f"Icon saved to:\n{ICO_PATH}\n\nDesktop shortcut created:\n{lnk}\n\n"
             "You can delete your old shortcut.")
    except Exception as e:
        log("ERROR: " + traceback.format_exc())
        show("error", "Could not finish", f"{e}\n\nDetails are in:\n{LOG_PATH}")


if __name__ == "__main__":
    main()