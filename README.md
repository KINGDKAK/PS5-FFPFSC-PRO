# PS5 FFPFSC PRO

A modern Windows GUI for compressing PS5 game folders into `.ffpfsc` archives using the Bizkut PS5 FFPFS compression backend.

---

## Features

✅ Modern Dark UI

✅ Drag & Drop Support

✅ Compression Ratings

✅ Stage Tracking

✅ Weighted Progress Reporting

✅ Storage Space Warnings

✅ Auto Cleanup

✅ Compression History

✅ Completion Notifications

✅ Detailed Logging

---

## Requirements

* Windows 10 / Windows 11
* Python 3.10+ (for source builds)
* Sufficient free disk space

---

## Download

Download the latest release from the Releases page.

Current Stable Release:

**PS5 FFPFSC PRO v1.0 Stable**

---

## How To Use

1. Launch **PS5_FFPFSC_PRO.exe**
2. Drag and drop a PS5 game folder into the application
3. Select an output folder
4. Click **Start Compression**
5. Wait for the compression process to complete
6. The resulting `.ffpfsc` file will be created in the output directory

---

## Compression Stages

### Stage 1 — Reading Game

The application scans the game folder and prepares files for processing.

### Stage 2 — Creating Temp File

The backend creates temporary PFS data required for compression.

⚠️ Important:

* This stage may appear frozen on large games
* Progress intentionally remains at 99% until the backend advances
* Do NOT close the application during this stage

### Stage 3 — Compressing

Game data is compressed into the final format.

### Stage 4 — Building Image

The compressed archive structure is assembled.

### Stage 5 — Writing Final Image

The final `.ffpfsc` file is written to disk.

### Stage 6 — Verification & Cleanup

Output validation and temporary file cleanup are performed.

---

## Storage Requirements

Large games may temporarily require up to approximately **2.2× the original game size** during compression.

Example:

| Game Size | Recommended Free Space |
| --------- | ---------------------- |
| 25 GB     | 55 GB                  |
| 50 GB     | 110 GB                 |
| 100 GB    | 220 GB                 |
| 150 GB    | 330 GB                 |

Temporary files are automatically cleaned after successful completion.

---

## Compression Ratings

After completion the application rates the compression result:

| Rating    | Savings      |
| --------- | ------------ |
| Excellent | 25%+         |
| Good      | 10%–25%      |
| Okay      | 5%–10%       |
| Poor      | Less than 5% |

Some games are already highly compressed and may not benefit significantly.

---

## Known Limitations

* Large games require significant temporary storage
* Compression does not improve game performance or load times
* Some titles may only achieve minimal size reduction

---

## Credits

Compression Backend:
Bizkut PS5 FFPFS CLI

Frontend:
PS5 FFPFSC PRO

Special thanks to everyone who tested the beta and release candidate builds.

---

## Disclaimer

This software is intended for archival, backup, preservation, and homebrew purposes only.

Users are responsible for complying with all applicable laws and regulations in their jurisdiction.
