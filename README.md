# Audiobook Player

A simple, good-looking desktop audiobook player for Windows, built with Python. It plays `.m4b` audiobooks with chapter support, remembers where you stopped in every book, and lets you pick your own light or dark theme and accent colour.

## Quick start

Anyone can use this app. If you already have Python and VLC, it takes under a minute:

1. Install the libraries: `pip install python-vlc mutagen pillow customtkinter`
2. Download this project (green **Code** button, then **Download ZIP**) and extract it.
3. Double-click **`audiobook.pyw`**.
4. *(Optional)* Double-click **`make_icon.pyw`** once to get a desktop shortcut with an icon.

New to Python or VLC? The [installation guide](#installation-step-by-step) below walks through everything from scratch.

## 100% free

- No subscription, no ads, no account, no sign-in.
- No tracking. The app never connects to the internet. Your books, covers and progress stay on your own computer.
- Everything it depends on (Python, VLC and the Python libraries below) is free and open source.

You only need your own audiobook files. Files protected by DRM (for example Audible `.aax` files) cannot be played; use DRM-free `.m4b`, `.m4a` or `.mp4` files.

## Features

- **A library of multiple books.** Add as many audiobooks as you like and switch between them with one click. Each book shows its cover art, author and how far through it you are.
- **Remembers your progress.** Your position is saved automatically in every book, so you can close the app, come back later, and carry on exactly where you left off. The last book you played reopens when you start the app.
- **Chapter support.** Chapters are read from the file and listed in the Chapters tab. Click any chapter to jump straight to it and start playing. The current chapter is highlighted as you listen.
- **Two seek bar modes.** Switch between:
  - **Chapter**: the seek bar covers only the current chapter, which is useful for precise seeking.
  - **Whole book**: the seek bar covers the entire book.
- **Time left and time done.** See the elapsed time and the time remaining. In chapter mode you also see how much of the whole book is left.
- **Playback controls.** Play and pause, previous and next chapter, skip back or forward 30 seconds, and a volume slider. Your volume is remembered.
- **Playback speed.** Change the speed from 0.5x to 3.0x in steps of 0.1. The speed is remembered separately for each book.
- **Keyboard shortcuts.** `Space` plays and pauses, `Left` and `Right` skip 30 seconds back and forward.
- **Details tab.** View the tags stored in the file (title, author, year, description and more) plus technical information such as codec, bitrate and file size.
- **Light and dark theme.** Switch between them at any time.
- **Custom accent colour.** Choose from preset colours or pick any colour you like. Your theme and colour are remembered.
- **Remove books.** Remove a book from your library whenever you want. Your audio file is never deleted.

## Requirements

- Windows 10 or 11 (developed and tested on Windows 11)
- Python 3 (tested with Python 3.14)
- VLC media player, which does the actual audio playback
- Four Python libraries: `python-vlc`, `mutagen`, `pillow` and `customtkinter`

Python and VLC must both be **64-bit** (or both 32-bit). Most computers today use 64-bit for both, and the steps below use that.

## Installation, step by step

### 1. Install Python

1. Go to <https://www.python.org/downloads/> and download the latest Python 3 installer for Windows (64-bit).
2. Run the installer.
3. **Important:** on the first screen, tick **"Add python.exe to PATH"** before clicking **Install Now**.
4. When it finishes, open the Start menu, type `cmd` and open **Command Prompt**. Type this and press Enter:

   ```
   python --version
   ```

   You should see a version number such as `Python 3.14.2`. If Windows says Python is not found, run the installer again, choose **Modify**, and make sure the PATH option is ticked.

### 2. Install VLC

1. Go to <https://www.videolan.org/vlc/> and download VLC for Windows.
2. Make sure you get the **64-bit** version. The download page's "Other systems" option lists both.
3. Run the installer with the default options. You do not need to open VLC afterwards; the player only uses it in the background.

Check that your Python is 64-bit by running this in Command Prompt:

```
python -c "import struct; print(struct.calcsize('P') * 8)"
```

It should print `64`. If it prints `32`, install the 32-bit version of VLC instead so the two match.

### 3. Install the Python libraries

In Command Prompt, run:

```
pip install python-vlc mutagen pillow customtkinter
```

| Library | What it is used for |
| --- | --- |
| `python-vlc` | Lets the app play audio through VLC |
| `mutagen` | Reads tags, covers and chapters from the audiobook file |
| `pillow` | Handles cover art and icons |
| `customtkinter` | The modern look of the app window |

If the `pip` command is not recognised, use `python -m pip install python-vlc mutagen pillow customtkinter` instead.

### 4. Get the app

Either:

- Click the green **Code** button on this page and choose **Download ZIP**, then extract it to a folder of your choice, or
- If you use Git: `git clone https://github.com/<your-username>/<repository-name>.git`

**Where to put the folder:** anywhere you like. There is no required location. Once Python, VLC and the libraries from steps 1 to 3 are installed, the app runs from any folder on any drive, such as Downloads, Documents, the Desktop or a USB drive.

Just keep these in mind:

- **Extract the ZIP first.** Do not run the app from inside the ZIP file. Right-click the download and choose **Extract All...**, then open the extracted folder.
- **Keep the files together.** `audiobook.pyw` and `make_icon.pyw` should stay in the same folder (the optional shortcut step relies on this).
- **Moving it later is safe.** Your library and progress are not stored in the app folder. They live in `.m4b_player` in your user folder (see [Where your data is stored](#where-your-data-is-stored)), so you can move or delete the app folder without losing them. If you made a desktop shortcut, run `make_icon.pyw` again from the new location so the shortcut points to the right place.
- **Your audiobooks can be anywhere too.** The app remembers each book by its location, so if you later move or rename a book file, the app will say it cannot find it. You will then need to remove that book and add it again from its new location, which starts its saved progress over. It is best to put your audiobooks in a folder you will not move.

### 5. Run it

Double-click **`audiobook.pyw`**. The app opens without a console window.

If nothing happens, open Command Prompt in the app's folder and run `python audiobook.pyw` instead. Any error message will then be shown in the window, which helps with troubleshooting (see below).

### 6. Create a desktop shortcut with an icon (optional)

The download includes a small helper, **`make_icon.pyw`**, that gives the app its own icon and puts a shortcut on your desktop, so you do not have to open the folder every time.

1. Make sure **`make_icon.pyw`** is in the **same folder** as **`audiobook.pyw`**. That is where it looks for the app, and it works wherever you keep that folder (Downloads, Documents, another drive, and so on).
2. Double-click **`make_icon.pyw`**. Nothing opens at first; it works in the background for a second or two.
3. A **Done** message appears. It does two things:
   - It draws the app icon (a purple rounded square with white headphones) and saves it as `audiobook.ico` in your `.m4b_player` folder.
   - It creates a shortcut called **Audiobook Player** on your desktop that starts the app without a console window and uses that icon.
4. From now on, start the app with that desktop shortcut. You can also right-click it and choose **Pin to Start** or **Pin to taskbar** (on Windows 11, you may need to click **Show more options** first).

You only need to do this once. Run `make_icon.pyw` again if you move the app folder to a new location or install a different version of Python, because the shortcut points to both. Running it again simply replaces the old shortcut.

`make_icon.pyw` only needs the `pillow` library from step 3 and Windows PowerShell, which every Windows 10 and 11 computer already has. It is Windows-only and will tell you so if you run it on anything else. If something goes wrong, the message box tells you what happened, and the details are saved in `make_icon.log` in the `.m4b_player` folder.

## How to use it

### Add books

1. Click **+ Add books** at the top of the Library.
2. Select one or more `.m4b`, `.m4a` or `.mp4` files. You can select several at once.
3. They appear in your library. Click a book to start playing it.

Click the book again later to resume it. Progress is saved automatically as you listen and when you pause or close the app.

### Listen

- Use the large round button to **play and pause**.
- Use the **previous** and **next chapter** buttons on either side of the skip buttons, or **-30s** and **+30s** to skip around.
- Change the **speed** with the **-** and **+** buttons on the left of the player bar.
- Change the **volume** with the slider on the right.

### Jump to a chapter

Open the **Chapters** tab on the right and click the chapter you want. Playback jumps there and starts straight away. You can also select a chapter with the arrow keys and press `Enter`.

### Switch between chapter and whole book seek bar

Use the **Chapter / Whole book** switch above the seek bar.

- In **Chapter** mode, the bar and the two time labels cover only the current chapter. The right-hand label shows what is left in the chapter, and the line above the bar on the right shows how much of the whole book is left.
- In **Whole book** mode, the bar and labels cover the entire book.

Drag the bar to seek. Your choice of mode is remembered. If a book has no chapters, the player uses Whole book mode automatically.

### See the progress of a book

- Each book in the Library has a progress bar and a percentage.
- The player bar shows the elapsed time on the left and the remaining time on the right.
- The middle of the window shows the book's total length and number of chapters.

### Change the theme and colours

1. Click the **gear button** next to **+ Add books**.
2. Choose **Dark** or **Light**.
3. Pick an accent colour from the presets, or click **Custom colour...** to choose any colour.

The changes apply immediately and are remembered the next time you open the app.

### View book details

Open the **Details** tab on the right to see the tags stored in the file and technical information about it. If a book shows no chapters, this tab also includes information that helps find out why.

### Remove a book

Select the book you want to remove (it is the one currently loaded) and click **Remove current book**. This removes it from your library and deletes its saved progress. The audio file itself stays on your computer, and you can add it again at any time.

## Where your data is stored

Everything is kept in a folder called `.m4b_player` inside your user folder, for example `C:\Users\YourName\.m4b_player`.

| File | Contents |
| --- | --- |
| `library.db` | Your library, progress, speeds and settings |
| `covers\` | Small cover thumbnails for the library list |
| `audiobook.ico` | The app icon, also used by the desktop shortcut |
| `error.log` | Details of any errors, useful if you report a problem |
| `make_icon.log` | Details from `make_icon.pyw`, if the shortcut could not be created |

To reset the app completely, close it and delete that folder. To move to another computer, copy the folder across.

## Troubleshooting

**"VLC could not be loaded"**
VLC is not installed, or Python and VLC do not match. Install VLC from <https://www.videolan.org/vlc/>, and make sure both are 64-bit (see step 2).

**"Missing package"**
Run `pip install python-vlc mutagen pillow customtkinter` in Command Prompt, then start the app again.

**`python` or `pip` is not recognised**
Python was installed without the PATH option. Run the Python installer again, choose **Modify**, and tick **Add python.exe to PATH**. If you only see the Microsoft Store when typing `python`, turn off the "App execution aliases" for Python in Windows Settings.

**A book plays but shows no chapters**
Not every audiobook file contains chapter information. The app reads Nero chapters, QuickTime chapter tracks and chapters reported by VLC. Open the **Details** tab to see what was found in the file.

**A book will not play**
The file may be DRM protected or damaged. Check that it plays in VLC itself.

**`make_icon.pyw` says it could not find `audiobook.pyw`**
Move `make_icon.pyw` into the same folder as `audiobook.pyw` and run it again.

**The desktop shortcut stopped working**
You probably moved the app folder or reinstalled Python. Double-click `make_icon.pyw` again to create a fresh shortcut.

**The app closes or behaves strangely**
Open `error.log` in the `.m4b_player` folder and include its contents if you report an issue.

## Feedback and contributions

Found a bug or have an idea? Open an issue on this repository's **Issues** tab. If it is a bug, please include what you were doing and the contents of `error.log` (see above). Pull requests are welcome.

## License

Released under the [MIT License](LICENSE). You are free to use, copy, modify and share this app, including for your own projects. Created by babyfacedassassin.

## Built with

- [Python](https://www.python.org/) and Tkinter
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) for the interface
- [VLC](https://www.videolan.org/vlc/) and [python-vlc](https://pypi.org/project/python-vlc/) for playback
- [mutagen](https://mutagen.readthedocs.io/) for reading tags and chapters
- [Pillow](https://python-pillow.org/) for images
