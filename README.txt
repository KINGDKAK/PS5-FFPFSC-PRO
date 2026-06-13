PS5 FFPFSC PRO v1.2.2
by KINGDKAK | Powered by Bizkut Backend

════════════════════════════════════════════════

HOW TO RUN (Python)
  Double-click RUN.bat
  Requires Python 3.10+ installed (python.org)

HOW TO BUILD EXE
  Double-click BUILD_EXE.bat
  Output: dist\PS5_FFPFSC_PRO.exe

════════════════════════════════════════════════

IMPORTANT
  Extract the ZIP fully before running.
  Do NOT run from inside the ZIP preview window.

════════════════════════════════════════════════

WHAT'S NEW IN v1.2.2
  See CHANGELOG.txt for full details.

  Highlights:
  - Stage display completely overhauled (no more stuck stages)
  - Critical proc.wait() loop bug fixed
  - Raw log flushed every 30s during run
  - Game name no longer shows parent folder (e.g. "PS5 DUMPS")
  - Community compat: deduplication + startup re-test reminder
  - ShadowMount guide updated with XMB shortcut warning (Step 1a)
  - Log no longer flooded with repeated 0% progress lines
  - .ffpkg disk images now supported (queue directly, no extraction)
  - Block size selector in Compression Tuning bar (auto/auto-fit/65536/32768/16384)
  - MkPFS v0.0.8 bundled — no pip install required
  - Error messages now include specific settings suggestions (CPU cores, Level, etc.)
  - Auto-worker-cap: >10 GB games cap at 4 cores, >30 GB cap at 2 (prevents OOM)
  - Log scroll: no longer auto-snaps to bottom while you're reading
  - --block-size only passed to mkpfs when non-default (fixes older pip mkpfs installs)

════════════════════════════════════════════════

VERIFY OUTPUT OPTION
  Leave "Verify Output" unchecked for normal use.
  Enable only if you want MkPFS post-build verification.
  Verification is slower and uses significantly more RAM —
  may cause MemoryError on systems with limited RAM.
