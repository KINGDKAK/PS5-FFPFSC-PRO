# PS5 FFPFSC PRO

![Platform](https://img.shields.io/badge/platform-Windows-blue)
![Backend](https://img.shields.io/badge/backend-MkPFS%20%2B%20FFPFSC-orange)
![Version](https://img.shields.io/badge/version-v1.3.0-green)

PS5 FFPFSC PRO is a Windows GUI for compressing PlayStation 5 game dumps using MkPFS and FFPFSC.

The goal is simple: make PS5 game compression easier without needing command-line tools or complicated setup.

---

## Features

* Compress PS5 game dumps into `.ffpfsc`
* Supports game folders, `.exfat`, `.ffpkg`, `.zip`, `.rar`, and `.7z`
* Drag-and-drop support
* Batch compression
* Compression tuning options
* Live RAM meter
* Auto update checker
* Community Compatibility Database
* Detailed logs and progress tracking
* Per-game output folders
* Compact mode

---

## Supported Inputs

* PS5 game folders
* `.exfat` images
* `.ffpkg` images
* `.zip` archives
* `.rar` archives
* `.7z` archives

---

## Community Compatibility Database

After a successful compression, you can optionally submit your result to the community database.

You can also browse and search compatibility reports from inside the app.

The database supports:

* Working / Partial / Not Working / Not Tested Yet status
* Searching by game name
* Searching by Title ID
* Report counts
* ShadowMount version info
* Vote-based results so one bad report does not override everyone else

---

## Compression Tuning

You can adjust:

* Compression level
* CPU cores
* Block size

Block size options:

* Auto
* Auto-Fit
* 16384
* 32768
* 65536

Smaller block sizes may help with games that have lots of small files.

---

## AMPR / APR Support

PS5 FFPFSC PRO can detect games that need the AMPR emulator.

It can detect PlayGo chunk files and includes a dedicated AMPR folder setting in Options.

---

## Getting Started

1. Download the latest release.
2. Run `PS5_FFPFSC_PRO.exe`.
3. Add a game folder, archive, `.exfat`, or `.ffpkg` image.
4. Pick your compression settings.
5. Click Start.

---

## Common Issues

### Out of Memory

Try lowering CPU cores or using a lower compression level.

### Disk Full

Make sure your Output and Temp folders have enough free space.

### Write Errors

Check that your output drive is writable and supports large files.

---

## Credits

Compression backend:

* MkPFS
* FFPFSC
* Bizkut

Thanks to everyone testing games, reporting bugs, and submitting compatibility results.

---

## Links

YouTube: https://youtube.com/@KINGDKAK

Ko-fi: https://ko-fi.com/KINGDKAK


---

## Disclaimer

This project is provided as-is.

Only use content you legally own and follow the laws in your region.

---

If the project helps you, consider starring the repo and submitting compatibility results for the community.
