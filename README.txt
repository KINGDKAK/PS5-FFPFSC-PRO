# PS5 FFPFSC PRO

PS5 FFPFSC PRO is a Windows GUI for compressing PlayStation 5 game dumps using MkPFS and FFPFSC.

The goal of the project is simple: make PS5 game compression easy without requiring command-line tools or complicated setup.

Whether you're compressing a single game, batch processing multiple titles, or checking community compatibility reports, everything can be done from a single interface.

---

## Features

### 📦 Compression

* Compress PS5 game dumps into `.ffpfsc`
* Powered by MkPFS and FFPFSC
* Batch compression support
* Compression tuning options
* Automatic retry on memory-related failures
* Compression statistics and space savings reports

### 📂 Supported Inputs

* PS5 game folders
* `.exfat` images
* `.ffpkg` images
* `.zip` archives
* `.rar` archives
* `.7z` archives

Drag-and-drop is fully supported.

---

## Community Compatibility Database

After a successful compression, you can optionally submit your results to the community database.

The database allows users to:

* Share compatibility results
* Report Working / Partial / Not Working status
* Search by game name
* Search by Title ID
* View report counts
* View ShadowMount version information

Compatibility status is vote-based, preventing a single incorrect report from overriding community results.

---

## Compression Tuning

Advanced users can fine-tune compression behavior using:

* Compression level selection
* CPU core selection
* Block size selection

  * Auto
  * Auto-Fit
  * 16384
  * 32768
  * 65536

Useful for optimizing compression speed, RAM usage, and results for games containing large numbers of small files.

---

## AMPR / APR Support

PS5 FFPFSC PRO can detect games that require the AMPR emulator.

* Automatic PlayGo chunk detection
* Dedicated AMPR folder configuration
* Compatibility reporting support

---

## Additional Features

* Live RAM usage monitor
* Automatic update checker
* Compact mode
* Resizable log panel
* Per-game output folders
* Detailed logging
* Changelog viewer
* Community database browser
* Multi-image queueing
* Ko-fi support integration

---

## Getting Started

1. Download the latest release.
2. Launch `PS5_FFPFSC_PRO.exe`
3. Add a game folder, archive, `.exfat`, or `.ffpkg` image.
4. Select your compression settings.
5. Click **Start**.

The application handles the rest.

---

## Common Issues

### Out of Memory

Try:

* Lowering CPU cores
* Lowering compression level
* Closing other applications

### Disk Full

Ensure sufficient free space exists in both:

* Output folder
* Temporary folder

### Write Errors

Verify that:

* Output locations are valid
* Drives are writable
* Storage devices have enough free space

The application provides detailed error messages and recommended fixes whenever possible.

---

## Credits

### Compression Backend

* MkPFS
* FFPFSC
* Bizkut

### Community

Special thanks to everyone testing games, submitting compatibility reports, reporting bugs, and helping improve the project.

---

## Links

📺 YouTube
https://youtube.com/@KINGDKAK

☕ Ko-fi
https://ko-fi.com/KINGDKAK

🐙 GitHub
https://github.com/juma-sayeh/PS5-Game-Compressor

---

## Disclaimer

This project is provided as-is.

Only use content you legally own and follow all applicable laws in your region.

---

⭐ If you find the project useful, consider starring the repository and contributing compatibility results to help the community.
