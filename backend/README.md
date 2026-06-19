# PS5 FFPFS-CLI

A cross-platform CLI and GUI tool to pack and build PS5 homebrew images in the `.ffpfsc` container format for ShadowMountPlus (SMP).

Rather than using complex, platform-dependent exFAT loopback mounts, this tool creates a standard **uncompressed PFS image (`pfs_image.dat`)** and packs it inside a **compressed PFS container (`.ffpfsc`)**, which is the recommended layout for nested images in ShadowMountPlus.

## Features

- **Pure Python & Cross-Platform**: Runs natively on macOS, Linux, and Windows with **zero** OS-specific dependencies.
- **No Admin/Root Privileges Required**: Since it doesn't need to mount loopback disks or format drives, it runs completely in userland.
- **Smart Folder Discovery**: You don't need to pass the exact game root. The tool recursively scans the provided directory for the actual game folder (containing `eboot.bin` and `sce_sys/param.json`).
- **Title ID Auto-Naming**: Automatically parses `sce_sys/param.json` to extract the game's actual Title ID (e.g., `PPSA01411`) and names output files accordingly.
- **Archive Support**: Directly process **ZIP** and **RAR** archives (including password-protected) without manual extraction. Uses a built-in, self-contained UnRAR C++ extension — no external `unrar` or `7-Zip` binaries required.
- **Batch Processing**: Process an entire directory of multiple games, archives, and `.exfat` files into separate images automatically using the `--batch` flag.
- **GUI Mode**: Launch a graphical user interface with `--gui` for a point-and-click workflow.
- **Auto-Cleanup**: Automatically cleans up intermediate nested PFS files, keeping only the final compressed `.ffpfsc` file.

## Download Prebuilt Binaries

Prebuilt standalone binaries are available on the [Releases](https://github.com/bizkut/ps5-ffpfs-cli/releases) page. No Python installation required.

| Platform | Download |
|----------|----------|
| Windows (x64) | `PS5-FFPFS-CLI-Windows-x64.exe` |
| macOS (universal) | `PS5-FFPFS-CLI-macOS-universal.zip` |
| Linux (x64) | `PS5-FFPFS-CLI-Linux-x64.AppImage` |

## Requirements (Source Install)

- Python 3.8+
- A C++ compiler (only needed to build the built-in `unrar` extension from source)

## Installation (Source)

```bash
git clone https://github.com/bizkut/ps5-ffpfs-cli.git
cd ps5-ffpfs-cli
pip install -e ./unrar
```

> The `unrar` directory contains a self-contained C++ extension for RAR extraction. It will be built automatically during `pip install`.

## CLI Usage

```bash
python3 cli.py [game_folder_or_archive_or_exfat] [output] [options]
```

### Options

| Flag | Description |
|------|-------------|
| `--keep-pfs` | Keep the intermediate nested PFS image (`<title_id>_nested_pfs.dat`) |
| `--batch` | Process multiple inputs into multiple outputs. `output` is treated as a directory. |
| `--gui` | Launch the graphical user interface |
| `-f`, `--force`, `--overwrite` | Overwrite existing files without prompting |
| `--password PASSWORD` | Password for ZIP/RAR archives |

### Examples

**Standard Process (Game Folder → .ffpfsc):**
```bash
python3 cli.py /path/to/GameFolder
```

**Process a Password-Protected RAR Archive:**
```bash
python3 cli.py /path/to/Game.rar --password DLPSGAME.COM
```

**Process a ZIP Archive:**
```bash
python3 cli.py /path/to/Game.zip
```

**Convert Existing exFAT (exFAT → .ffpfsc):**
```bash
python3 cli.py /path/to/GameImage.exfat
```

**Batch Processing:**
```bash
python3 cli.py /path/to/AllGames /path/to/OutputFolder --batch
```

**Keep Intermediate Files:**
```bash
python3 cli.py /path/to/GameFolder --keep-pfs
```

**Launch GUI:**
```bash
python3 cli.py --gui
```

## GUI Usage

Launch the GUI either by running the standalone executable (no terminal needed) or from the command line:

```bash
python3 gui.py
```

The GUI supports:
- Selecting source folders, archives, or `.exfat` files via a file picker
- Password input for protected archives
- Batch folder selection
- Output directory selection
- Progress feedback during packing

## Building from Source

### Build Standalone Executable (via PyInstaller)

```bash
pip install pyinstaller
pyinstaller --name PS5-FFPFS-CLI --onefile --windowed \
  --hidden-import tkinter --hidden-import mkpfs.cli \
  --hidden-import unrar --hidden-import unrar.rarfile --hidden-import unrar._unrar \
  --collect-data tkinter --collect-binaries tkinter \
  --collect-data customtkinter --collect-data mkpfs --collect-binaries mkpfs \
  gui.py
```

## License

MIT License. The built-in UnRAR extension is based on the RARLAB UnRAR source (freeware license for extraction-only use).
