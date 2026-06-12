
from __future__ import annotations

import os
import re
import sys
import time
import json
import queue
import zipfile
import threading
import subprocess
import shutil
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk

try:
    import customtkinter as ctk
except ImportError:
    raise SystemExit("Missing customtkinter. Run: py -m pip install customtkinter")

try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None

try:
    import winsound
except Exception:
    winsound = None

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _HAS_DND = True
except Exception:
    TkinterDnD = None
    DND_FILES = None
    _HAS_DND = False

APP_NAME = "PS5 FFPFSC PRO"
APP_VERSION = "1.2.2"
BACKEND_NAME = "bizkut/ps5-ffpfs-cli"
MKPFS_NAME    = "MkPFS"
MKPFS_VERSION = "0.0.8"

APP_DIR = Path(os.getenv("APPDATA", str(Path.home()))) / "PS5_FFPFSC_PRO_BIZKUT"
RAW_LOG_FILE = APP_DIR / "raw_tool_output.log"
FINAL_REPORT_FILE = APP_DIR / "last_result_report.txt"
HISTORY_FILE = APP_DIR / "history.json"
SETTINGS_FILE = APP_DIR / "settings.json"
COMPAT_FILE = APP_DIR / "compatibility.json"
COMMUNITY_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbzUxOxhfNi3cGs2cP1tlX1etWbj62neOuS_mOOnL8ipPaBhNH_weoIJPPiF-wCIBkOH/exec"
)

TITLE_RE = re.compile(r"\b(PPSA\d{5}|CUSA\d{5})\b", re.I)
PROGRESS_RE = re.compile(r"\[(?P<bar>[#\-]{4,})\]\s*(?P<pct>\d{1,3})%\s*(?P<label>.*)", re.I)

# Each constant is a (light_mode, dark_mode) tuple.
# CTk reads the correct value automatically when set_appearance_mode() is called —
# no manual recoloring needed anywhere in the app.
BLACK   = ("#f0f0f0", "#050505")   # main background
PANEL   = ("#e2e2e2", "#111111")   # panel / card background
CARD    = ("#d4d4d4", "#151515")   # entry / inner card
CARD2   = ("#cacaca", "#1a1a1a")   # secondary card / normal button fill
BORDER  = ("#b0b0b0", "#2a2a2a")   # panel border
BORDER2 = ("#999999", "#3a3a3a")   # entry / button border
GREEN   = "#4ade80"                 # accent — looks fine on both backgrounds
GREEN2  = "#22c55e"                 # accent hover
YELLOW  = "#facc15"
RED     = "#ef4444"
WHITE   = ("#111111", "#f8fafc")   # primary text  (dark text in light mode)
MUTED   = ("#555555", "#a1a1aa")   # secondary text


def ensure_app_dir() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)


def open_path(path) -> None:
    """Open a file or folder with the default OS handler (cross-platform)."""
    p = str(path)
    try:
        if os.name == "nt":
            os.startfile(p)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p])
        else:
            subprocess.Popen(["xdg-open", p])
    except Exception:
        pass


def now_time() -> str:
    return time.strftime("%H:%M:%S")


def now_datetime() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def format_size(num) -> str:
    try:
        num = float(num)
    except Exception:
        return "—"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num < 1024 or unit == "TB":
            return f"{num:.2f} {unit}" if unit != "B" else f"{num:.0f} {unit}"
        num /= 1024


def format_duration(seconds) -> str:
    seconds = int(max(0, seconds))
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def get_free_space(path: Path) -> int:
    try:
        target = path if path.exists() else path.parent
        usage = shutil.disk_usage(str(target))
        return usage.free
    except Exception:
        return 0


def get_total_space(path: Path) -> int:
    try:
        target = path if path.exists() else path.parent
        usage = shutil.disk_usage(str(target))
        return usage.total
    except Exception:
        return 0


def same_drive(path_a: Path, path_b: Path) -> bool:
    try:
        return path_a.resolve().drive.lower() == path_b.resolve().drive.lower()
    except Exception:
        return str(path_a)[:2].lower() == str(path_b)[:2].lower()


def estimate_peak_space_needed(game_size: int, same_temp_output_drive: bool = True) -> int:
    return int(game_size * (2.20 if same_temp_output_drive else 1.20))


def get_folder_size(path: Path) -> int:
    return folder_size(path) if path.exists() else 0


def find_newest_ffpfsc_after(folder: Path, started_at: float):
    try:
        if not folder.exists():
            return None
        candidates = []
        for p in folder.glob("*.ffpfsc"):
            try:
                if p.is_file() and p.stat().st_size > 0 and p.stat().st_mtime >= started_at - 2:
                    candidates.append(p)
            except OSError:
                pass
        if not candidates:
            return None
        return max(candidates, key=lambda x: x.stat().st_mtime)
    except Exception:
        return None


def compression_rating(saved_pct: float) -> tuple[str, str]:
    if saved_pct >= 25:
        return "EXCELLENT", "Great compression candidate. This title is worth keeping compressed."
    if saved_pct >= 10:
        return "GOOD", "Good result. Compression is likely worth it."
    if saved_pct >= 5:
        return "OKAY", "Small but usable savings. Keep only if storage is tight."
    return "POOR", "Not worth compressing. This title is already highly compressed or not a good candidate."


def get_drive_type(path: Path) -> str:
    """Detect SSD/NVMe vs HDD using PowerShell. Returns 'SSD', 'HDD', or 'Unknown'."""
    if os.name != "nt":
        return "Unknown"
    try:
        drive_letter = path.resolve().drive.rstrip(":\\")
        if not drive_letter:
            return "Unknown"
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-Partition -DriveLetter '{drive_letter}' | Get-Disk | Select-Object -ExpandProperty MediaType"],
            capture_output=True, text=True, timeout=6,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        media = result.stdout.strip().upper()
        if "SSD" in media or "NVM" in media:
            return "SSD"
        if "HDD" in media or "UNSPECIFIED" in media:
            # Unspecified on some systems means HDD
            if "UNSPECIFIED" in media:
                # Try bus type to distinguish
                result2 = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     f"Get-Partition -DriveLetter '{drive_letter}' | Get-Disk | Select-Object -ExpandProperty BusType"],
                    capture_output=True, text=True, timeout=6,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                bus = result2.stdout.strip().upper()
                if "NVME" in bus or "SATA" in bus:
                    return "SSD"
                if "ATA" in bus:
                    return "HDD"
            return "HDD"
    except Exception:
        pass
    return "Unknown"


def get_filesystem_type(path: Path) -> str:
    """Return filesystem label (NTFS, exFAT, FAT32 …) using GetVolumeInformationW."""
    if os.name != "nt":
        return "Unknown"
    try:
        import ctypes
        target = path if path.exists() else path.parent
        drive = str(target.resolve()).split("\\")[0] + "\\"  # e.g. "C:\\"
        buf = ctypes.create_unicode_buffer(64)
        ctypes.windll.kernel32.GetVolumeInformationW(
            drive, None, 0, None, None, None, buf, ctypes.sizeof(buf)
        )
        return buf.value.strip() or "Unknown"
    except Exception:
        return "Unknown"


def is_game_folder(path: Path) -> bool:
    """Return True if *path* looks like a PS5 game folder."""
    return path.is_dir() and (path / "sce_sys").is_dir() and (path / "eboot.bin").is_file()


def find_game_folders(root: Path, max_depth: int = 3) -> list[Path]:
    """Recursively find all PS5 game subfolders under *root* (up to max_depth levels)."""
    found: list[Path] = []

    def _scan(path: Path, depth: int) -> None:
        if depth > max_depth:
            return
        if is_game_folder(path):
            found.append(path)
            return  # don't recurse inside a game folder
        try:
            for child in sorted(path.iterdir()):
                if child.is_dir() and not child.name.startswith("."):
                    _scan(child, depth + 1)
        except (PermissionError, OSError):
            pass

    _scan(root, 0)
    return found


def validate_game_structure(path: Path) -> list[str]:
    """Return a list of human-readable warnings for incomplete PS5 game folders."""
    warnings: list[str] = []
    sce_sys   = path / "sce_sys"
    param_json = sce_sys / "param.json"
    eboot     = path / "eboot.bin"
    if not sce_sys.is_dir():
        warnings.append("sce_sys folder not found — this may not be a PS5 game dump.")
    elif not param_json.is_file():
        warnings.append("sce_sys/param.json missing — ShadowMount compatibility not guaranteed.")
    if not eboot.is_file():
        warnings.append("eboot.bin not found — the dump may be incomplete.")
    return warnings


# Maps log keywords → user-friendly cause + fix
_ERROR_PATTERNS: list[tuple[str, str]] = [
    ("unable to stage source file",
     "Temp drive does not support hardlinks or symlinks.\n"
     "Fix: use a temp folder on an NTFS-formatted SSD/NVMe."),
    ("hard link and symlink both failed",
     "Temp drive does not support hardlinks or symlinks.\n"
     "Fix: use a temp folder on an NTFS-formatted SSD/NVMe."),
    ("memoryerror",
     "Not enough RAM during compression.\n"
     "Fix: close other apps, or disable 'Verify Output'."),
    ("no space left on device",
     "Drive ran out of space mid-compression.\n"
     "Fix: free up space on the temp or output drive."),
    ("no such file or directory",
     "A required file was not found — the game folder may be incomplete."),
    ("could not find any valid game",
     "No valid PS5 game folders detected.\n"
     "Fix: select the folder that contains sce_sys and eboot.bin."),
    ("missing/invalid param.json",
     "param.json is missing or corrupt — not a valid PS5 game dump."),
    ("permission denied",
     "Access denied.\n"
     "Fix: run as administrator, or move files off a read-only drive."),
    ("winerror 5",
     "Access denied (WinError 5).\n"
     "Fix: run as administrator."),
    ("winerror 1",
     "Windows system error (WinError 1).\n"
     "Fix: run as administrator."),
    ("calledprocesserror",
     "A backend subprocess failed — check the raw log for details."),
]


def smart_error_from_log() -> str:
    """Scan the raw log file and return a user-friendly error string, or ''."""
    if not RAW_LOG_FILE.exists():
        return ""
    try:
        text = RAW_LOG_FILE.read_text(encoding="utf-8", errors="ignore").lower()
    except Exception:
        return ""
    for keyword, message in _ERROR_PATTERNS:
        if keyword in text:
            return message
    return ""


def get_backend_python_command() -> list[str]:
    if getattr(sys, "frozen", False):
        py_launcher = shutil.which("py")
        if py_launcher:
            return [py_launcher, "-3"]
        python_exe = shutil.which("python")
        if python_exe:
            return [python_exe]
        python_exe = shutil.which("python3")
        if python_exe:
            return [python_exe]
        return []
    return [sys.executable]


def backend_base_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "backend"
    return Path(__file__).resolve().parent / "backend"


def folder_size(path: Path) -> int:
    total = 0
    try:
        if path.is_file():
            return path.stat().st_size
        for p in path.rglob("*"):
            try:
                if p.is_file():
                    total += p.stat().st_size
            except OSError:
                pass
    except Exception:
        pass
    return total


def file_count(path: Path) -> int:
    try:
        if path.is_file():
            return 1
        return sum(1 for p in path.rglob("*") if p.is_file())
    except Exception:
        return 0


def parse_title_id(path: Path) -> str:
    m = TITLE_RE.search(str(path))
    if m:
        return m.group(1).upper()
    try:
        for p in path.rglob("param.json"):
            text = p.read_text(encoding="utf-8", errors="ignore")
            m = TITLE_RE.search(text)
            if m:
                return m.group(1).upper()
    except Exception:
        pass
    return "Unknown"


def guess_game_name(path: Path) -> str:
    # 1. Try param.json for the real localised title first
    for candidate in (path / "sce_sys" / "param.json",
                      path / "sce_sys" / "param.sfo"):   # sfo handled below
        pass  # only param.json is plaintext
    param = path / "sce_sys" / "param.json"
    if param.exists():
        try:
            import json as _json
            data = _json.loads(param.read_text(encoding="utf-8", errors="replace"))
            # param.json structure: {"titleId":..., "localizedParameters":{"defaultLanguage":"en-US", "en-US":{"titleName":"..."}}}
            loc = data.get("localizedParameters", {})
            default_lang = loc.get("defaultLanguage", "")
            title = (loc.get(default_lang, {}).get("titleName", "")
                     or loc.get("en-US", {}).get("titleName", "")
                     or next((v.get("titleName", "") for v in loc.values()
                               if isinstance(v, dict) and v.get("titleName")), ""))
            if title:
                return title.strip()
        except Exception:
            pass

    # 2. Fall back to folder name, cleaning up common PS5 dump suffixes
    name = path.name
    # Strip "-app" / "_app" suffix (e.g. PPSA04264-app → PPSA04264)
    # Do NOT use parent folder — it is often a generic dump dir like "PS5 DUMPS"
    name = re.sub(r"[-_]app$", "", name, flags=re.I)
    name = re.sub(r"\s*\[.*?\]\s*", " ", name)
    name = re.sub(r"-\[.*?\]", "", name)
    return name.replace("_", " ").strip(" -") or path.name


def find_artwork(path: Path):
    if path.is_file():
        return None
    for name in ["icon0.png", "pic0.png", "pic1.png"]:
        try:
            hits = list(path.rglob(name))
            if hits:
                return hits[0]
        except Exception:
            pass
    return None


def load_history():
    ensure_app_dir()
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_history(items):
    ensure_app_dir()
    HISTORY_FILE.write_text(json.dumps(items[-100:], indent=2), encoding="utf-8")


def load_settings() -> dict:
    ensure_app_dir()
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_settings(data: dict) -> None:
    ensure_app_dir()
    existing = load_settings()
    existing.update(data)
    SETTINGS_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def is_first_run() -> bool:
    return not SETTINGS_FILE.exists()


# ── Compatibility list helpers ─────────────────────────────────────────────────

def load_compat() -> list:
    ensure_app_dir()
    try:
        if COMPAT_FILE.exists():
            return json.loads(COMPAT_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def save_compat(reports: list) -> None:
    ensure_app_dir()
    COMPAT_FILE.write_text(json.dumps(reports, indent=2, ensure_ascii=False), encoding="utf-8")


def add_compat_report(report: dict) -> None:
    reports = load_compat()
    tid = report.get("title_id", "").strip().upper()
    if tid:
        # Replace any existing local entry for the same title — don't accumulate duplicates
        reports = [r for r in reports if r.get("title_id", "").strip().upper() != tid]
    reports.insert(0, report)          # newest first
    save_compat(reports)


def get_last_log_lines(n: int = 50) -> str:
    try:
        if RAW_LOG_FILE.exists():
            lines = RAW_LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
            return "\n".join(lines[-n:])
    except Exception:
        pass
    return ""


# ─── First Run Wizard ──────────────────────────────────────────────────────────

class FirstRunWizard(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("PS5 FFPFSC PRO — First Run Setup")
        self.geometry("640x520")
        self.resizable(False, False)
        self.grab_set()
        self.configure(fg_color=BLACK)

        self.step = 0
        self.temp_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.result = {}

        self._build()
        self._show_step(0)

    def _build(self):
        self.header = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=22, weight="bold"), text_color=WHITE)
        self.header.pack(pady=(24, 6), padx=30, anchor="w")

        self.sub = ctk.CTkLabel(self, text="", text_color=MUTED, wraplength=580, justify="left")
        self.sub.pack(padx=30, anchor="w")

        self.body = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=10)
        self.body.pack(fill="both", expand=True, padx=30, pady=18)

        nav = ctk.CTkFrame(self, fg_color=BLACK)
        nav.pack(fill="x", padx=30, pady=(0, 20))
        nav.grid_columnconfigure(1, weight=1)
        self.back_btn = ctk.CTkButton(nav, text="← Back", width=100, fg_color=CARD2, text_color=WHITE,
                                       hover_color=("#b0b0b0", "#2a2a2a"), command=self._back)
        self.back_btn.grid(row=0, column=0, padx=(0, 8))
        self.next_btn = ctk.CTkButton(nav, text="Next →", width=100, fg_color=GREEN,
                                       text_color="#061006", hover_color=GREEN2, command=self._next)
        self.next_btn.grid(row=0, column=2)

        self.step_var = tk.StringVar(value="Step 1 of 4")
        ctk.CTkLabel(nav, textvariable=self.step_var, text_color=MUTED).grid(row=0, column=1)

    def _clear_body(self):
        for w in self.body.winfo_children():
            w.destroy()

    def _show_step(self, n):
        self.step = n
        self.step_var.set(f"Step {n + 1} of 4")
        self.back_btn.configure(state="normal" if n > 0 else "disabled")
        self.next_btn.configure(text="Finish" if n == 3 else "Next →")
        self._clear_body()

        if n == 0:
            self.header.configure(text="Step 1 — Select Temp Folder")
            self.sub.configure(text="Choose a temp folder on a fast SSD or NVMe drive. Avoid mechanical HDDs for large games.")
            ctk.CTkLabel(self.body, text="Temp Folder:", text_color=WHITE).pack(anchor="w", padx=14, pady=(14, 4))
            row = ctk.CTkFrame(self.body, fg_color=PANEL)
            row.pack(fill="x", padx=14)
            row.grid_columnconfigure(0, weight=1)
            ctk.CTkEntry(row, textvariable=self.temp_path, fg_color=CARD, border_color=BORDER2, text_color=WHITE).grid(row=0, column=0, sticky="ew", padx=(0, 8))
            ctk.CTkButton(row, text="Browse", width=80, fg_color=CARD2, text_color=WHITE, hover_color=("#b0b0b0", "#2a2a2a"),
                           command=self._browse_temp).grid(row=0, column=1)

        elif n == 1:
            self.header.configure(text="Step 2 — Select Output Folder")
            self.sub.configure(text="Choose where compressed .ffpfsc files will be saved. This can be an external drive or the same drive.")
            ctk.CTkLabel(self.body, text="Output Folder:", text_color=WHITE).pack(anchor="w", padx=14, pady=(14, 4))
            row = ctk.CTkFrame(self.body, fg_color=PANEL)
            row.pack(fill="x", padx=14)
            row.grid_columnconfigure(0, weight=1)
            ctk.CTkEntry(row, textvariable=self.output_path, fg_color=CARD, border_color=BORDER2, text_color=WHITE).grid(row=0, column=0, sticky="ew", padx=(0, 8))
            ctk.CTkButton(row, text="Browse", width=80, fg_color=CARD2, text_color=WHITE, hover_color=("#b0b0b0", "#2a2a2a"),
                           command=self._browse_output).grid(row=0, column=1)

        elif n == 2:
            self.header.configure(text="Step 3 — Storage Check")
            self.sub.configure(text="Checking your selected drives for speed and available space.")
            lines = []
            tp = self.temp_path.get().strip()
            op = self.output_path.get().strip()
            if tp:
                tpath = Path(tp)
                ttype = get_drive_type(tpath)
                tfree = get_free_space(tpath)
                lines.append(f"Temp Drive:    {format_size(tfree)} free  |  Type: {ttype}")
                if ttype == "HDD":
                    lines.append("  ⚠  Temp folder is on a mechanical HDD.\n     Large games may process significantly slower.\n     SSD/NVMe recommended.")
            if op:
                opath = Path(op)
                ofree = get_free_space(opath)
                lines.append(f"Output Drive:  {format_size(ofree)} free")
            if not lines:
                lines.append("No paths selected. Go back and select folders.")
            for line in lines:
                color = YELLOW if "⚠" in line else WHITE
                ctk.CTkLabel(self.body, text=line, text_color=color, anchor="w",
                              font=ctk.CTkFont(family="Consolas", size=12),
                              justify="left").pack(anchor="w", padx=14, pady=3)

        elif n == 3:
            self.header.configure(text="Step 4 — Ready!")
            self.sub.configure(text="Setup is complete. These settings will be saved and pre-filled next time you launch.")
            summary = []
            if self.temp_path.get():
                summary.append(f"Temp Folder:    {self.temp_path.get()}")
            if self.output_path.get():
                summary.append(f"Output Folder:  {self.output_path.get()}")
            summary.append("")
            summary.append("Click Finish to launch PS5 FFPFSC PRO.")
            for line in summary:
                ctk.CTkLabel(self.body, text=line, text_color=WHITE, anchor="w",
                              font=ctk.CTkFont(family="Consolas", size=12)).pack(anchor="w", padx=14, pady=2)

    def _browse_temp(self):
        p = filedialog.askdirectory(title="Select Temp Folder")
        if p:
            self.temp_path.set(str(Path(p) / "_ffpfsc_temp"))

    def _browse_output(self):
        p = filedialog.askdirectory(title="Select Output Folder")
        if p:
            self.output_path.set(p)

    def _back(self):
        if self.step > 0:
            self._show_step(self.step - 1)

    def _next(self):
        if self.step < 3:
            self._show_step(self.step + 1)
        else:
            self.result = {
                "temp_folder": self.temp_path.get(),
                "output_folder": self.output_path.get(),
                "first_run_done": True,
            }
            save_settings(self.result)
            self.destroy()


# ─── Detailed Error Dialog ─────────────────────────────────────────────────────

class ErrorDialog(ctk.CTkToplevel):
    def __init__(self, parent, msg: str, last_cmd: str = "", log_lines: str = ""):
        super().__init__(parent)
        self.title("Compression Failed")
        self.geometry("700x560")
        self.resizable(True, True)
        self.grab_set()
        self.configure(fg_color=BLACK)
        self._msg = msg
        self._cmd = last_cmd
        self._log = log_lines
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="Compression Failed", font=ctk.CTkFont(size=22, weight="bold"),
                      text_color=RED).pack(anchor="w", padx=20, pady=(20, 4))

        ctk.CTkLabel(self, text=self._msg, text_color=WHITE, wraplength=660, justify="left").pack(anchor="w", padx=20, pady=(0, 10))

        causes = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=8)
        causes.pack(fill="x", padx=20, pady=(0, 12))
        ctk.CTkLabel(causes, text="Possible Causes:", text_color=YELLOW,
                      font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=14, pady=(10, 4))
        for cause in [
            "• Insufficient free space on temp or output drive",
            "• External drive disconnected or write-protected",
            "• Temp folder unavailable or permissions issue",
            "• MkPFS backend failure (corrupted dump or unsupported format)",
            "• Python not found or wrong version",
            "• Antivirus blocking backend process",
        ]:
            ctk.CTkLabel(causes, text=cause, text_color=MUTED, anchor="w").pack(anchor="w", padx=24, pady=1)
        ctk.CTkFrame(causes, height=8, fg_color=PANEL).pack()

        ctk.CTkLabel(self, text="Last 50 Log Lines:", text_color=WHITE,
                      font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=20, pady=(0, 4))
        box = ctk.CTkTextbox(self, fg_color=BLACK, text_color=("#1a7a40", "#4ade80"), border_width=1, border_color=BORDER,
                              font=ctk.CTkFont(family="Consolas", size=11), height=160, wrap="none")
        box.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        box.insert("end", self._log or "(No log available)")
        box.configure(state="disabled")

        btns = ctk.CTkFrame(self, fg_color=BLACK)
        btns.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkButton(btns, text="Copy Error", width=140, fg_color=CARD2, text_color=WHITE,
                       hover_color=("#b0b0b0", "#2a2a2a"), command=self._copy).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btns, text="Export Raw Log", width=140, fg_color=CARD2, text_color=WHITE,
                       hover_color=("#b0b0b0", "#2a2a2a"), command=self._export_log).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btns, text="Open Log Folder", width=140, fg_color=CARD2, text_color=WHITE,
                       hover_color=("#b0b0b0", "#2a2a2a"), command=self._open_folder).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btns, text="Close", width=100, fg_color=RED, text_color=WHITE,
                       hover_color=("#b91c1c", "#5a1a1a"), command=self.destroy).pack(side="right")

    def _copy(self):
        text = f"Error: {self._msg}\n\nLast Command: {self._cmd}\n\nLog:\n{self._log}"
        self.clipboard_clear()
        self.clipboard_append(text)

    def _export_log(self):
        ensure_app_dir()
        if RAW_LOG_FILE.exists():
            open_path(RAW_LOG_FILE)

    def _open_folder(self):
        ensure_app_dir()
        open_path(APP_DIR)


# ─── Summary Dialog ────────────────────────────────────────────────────────────

class SummaryDialog(ctk.CTkToplevel):
    """Compression result summary with copy-to-clipboard button."""

    def __init__(self, parent, report: str):
        super().__init__(parent)
        self.title("Compression Complete")
        self.configure(fg_color=BLACK)
        self.resizable(True, True)
        self.geometry("580x460")
        self.lift()
        self.focus_force()
        self.grab_set()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self, text="✅  Compression Complete",
                      text_color=GREEN, font=ctk.CTkFont(size=18, weight="bold"),
                      anchor="w").grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 6))

        box = ctk.CTkTextbox(self, fg_color=CARD, border_width=1, border_color=BORDER2,
                              text_color=WHITE, font=ctk.CTkFont(family="Consolas", size=12),
                              wrap="word")
        box.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 8))
        box.insert("1.0", report)
        box.configure(state="disabled")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)

        def _copy():
            self.clipboard_clear()
            self.clipboard_append(report)
            copy_btn.configure(text="✓ Copied!")
            self.after(2000, lambda: copy_btn.configure(text="📋  Copy Result"))

        copy_btn = ctk.CTkButton(btn_row, text="📋  Copy Result", command=_copy,
                                  fg_color=CARD2, hover_color=("#b0b0b0", "#2a2a2a"),
                                  text_color=WHITE, border_width=1, border_color=BORDER2)
        copy_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(btn_row, text="Close", command=self.destroy,
                       fg_color=GREEN, hover_color=GREEN2,
                       text_color="#061006").grid(row=0, column=1, sticky="ew")


# ─── Space Diagnostics Dialog ──────────────────────────────────────────────────

class SpaceDiagnosticsDialog(ctk.CTkToplevel):
    """Pre-flight space check shown before compression starts.
    Opens instantly — drive-type detection runs in a background thread."""

    def __init__(self, parent, item, temp_dir: Path, out_dir: Path):
        super().__init__(parent)
        self.title("Drive Space Diagnostics")
        self.geometry("520x450")
        self.resizable(False, False)
        self.configure(fg_color=BLACK)
        self.proceed = False
        self._auto_timer = None
        self._countdown  = 0
        self._proceed_btn = None   # set in _build
        self._build(item, temp_dir, out_dir)
        # Keep dialog above the main window on all platforms
        self.transient(parent)
        self.lift()
        self.focus_force()
        self.after(50, self.grab_set)
        # Auto-proceed after 4 s when space is sufficient
        if get_free_space(temp_dir) >= estimate_peak_space_needed(
                item.size, same_drive(temp_dir, out_dir)):
            self._countdown = 4
            self.after(1000, self._tick_countdown)

    def _build(self, item, temp_dir: Path, out_dir: Path):
        ctk.CTkLabel(self, text="Drive Space Diagnostics",
                      font=ctk.CTkFont(size=20, weight="bold"),
                      text_color=WHITE).pack(anchor="w", padx=20, pady=(18, 2))
        ctk.CTkLabel(self, text="Pre-flight check before compression starts.",
                      text_color=MUTED).pack(anchor="w", padx=20, pady=(0, 10))

        panel = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=10)
        panel.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        # ── Fast values (no blocking) ──────────────────────────────────────────
        temp_free   = get_free_space(temp_dir)
        out_free    = get_free_space(out_dir)
        same        = same_drive(temp_dir, out_dir)
        peak_needed = estimate_peak_space_needed(item.size, same)
        final_est   = int(item.size * 0.55)
        temp_fs     = get_filesystem_type(temp_dir)   # fast ctypes call
        out_fs      = get_filesystem_type(out_dir)

        def _fs_status(fs):
            if fs in ("exFAT", "FAT32", "FAT"): return "warn"
            if fs == "NTFS": return "ok"
            return None

        def _color(status):
            if status == "ok":   return ("#1a7a40", "#4ade80")
            if status == "warn": return YELLOW
            return WHITE

        space_ok = temp_free >= peak_needed

        static_rows = [
            ("Game Size",          format_size(item.size),                  None),
            ("Temp Drive Free",    format_size(temp_free),                  None),
            ("Output Drive Free",  format_size(out_free),                   None),
            ("Est. Peak Required", format_size(peak_needed),
             "ok" if space_ok else "warn"),
            ("Est. Final Output",  f"~{format_size(final_est)} (typical)",  None),
            ("Temp Filesystem",    temp_fs,    _fs_status(temp_fs)),
            ("Output Filesystem",  out_fs,     _fs_status(out_fs)),
        ]

        for lbl, val, st in static_rows:
            row = ctk.CTkFrame(panel, fg_color=PANEL)
            row.pack(fill="x", padx=14, pady=2)
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(row, text=lbl + ":", text_color=MUTED,
                          anchor="w", width=200).grid(row=0, column=0, sticky="w")
            ctk.CTkLabel(row, text=val, text_color=_color(st),
                          anchor="e").grid(row=0, column=1, sticky="e")

        # ── Drive type row — populated by background thread ───────────────────
        dt_row = ctk.CTkFrame(panel, fg_color=PANEL)
        dt_row.pack(fill="x", padx=14, pady=2)
        dt_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(dt_row, text="Temp Drive Type:", text_color=MUTED,
                      anchor="w", width=200).grid(row=0, column=0, sticky="w")
        self._dt_label = ctk.CTkLabel(dt_row, text="Detecting…", text_color=MUTED,
                                       anchor="e")
        self._dt_label.grid(row=0, column=1, sticky="e")

        # ── Space result banner ────────────────────────────────────────────────
        result_text  = "✓  Enough space to proceed." if space_ok else "⚠  Not enough space — compression may fail."
        result_color = ("#1a7a40", "#4ade80") if space_ok else YELLOW
        ctk.CTkLabel(panel, text=result_text, text_color=result_color,
                      font=ctk.CTkFont(size=13, weight="bold")
                     ).pack(anchor="w", padx=14, pady=(8, 2))

        # Filesystem warnings (fast — already have temp_fs / out_fs)
        if temp_fs in ("exFAT", "FAT32", "FAT"):
            ctk.CTkLabel(panel,
                          text=f"⚠  Temp drive is {temp_fs} — no hardlink support. Slower copy mode will be used.",
                          text_color=YELLOW, justify="left", wraplength=460
                         ).pack(anchor="w", padx=14, pady=(0, 2))
        if out_fs in ("exFAT", "FAT32", "FAT"):
            ctk.CTkLabel(panel,
                          text=f"⚠  Output drive is {out_fs}. NTFS recommended.",
                          text_color=YELLOW, justify="left", wraplength=460
                         ).pack(anchor="w", padx=14, pady=(0, 2))

        # HDD warning label — shown/hidden by background thread result
        self._hdd_warn = ctk.CTkLabel(panel,
                                       text="⚠  Temp folder is on a mechanical HDD — will be significantly slower.",
                                       text_color=YELLOW, justify="left", wraplength=460)
        # packed conditionally in background callback

        # ── Buttons ───────────────────────────────────────────────────────────
        btns = ctk.CTkFrame(self, fg_color=BLACK)
        btns.pack(fill="x", padx=20, pady=(0, 16))

        self._proceed_btn = ctk.CTkButton(btns, text="▶  START NOW",
                       fg_color=GREEN, hover_color=GREEN2,
                       text_color="#061006",
                       font=ctk.CTkFont(size=14, weight="bold"),
                       height=38,
                       command=self._ok
                      )
        self._proceed_btn.pack(side="right", padx=(8, 0))
        ctk.CTkButton(btns, text="Cancel",
                       fg_color=CARD2, text_color=WHITE,
                       hover_color=("#b0b0b0", "#2a2a2a"),
                       command=self._cancel
                      ).pack(side="right")

        # ── Background thread: drive type detection ───────────────────────────
        def _detect():
            dt = get_drive_type(temp_dir)   # may block up to 6 s
            try:
                self.after(0, lambda: self._apply_drive_type(dt))
            except Exception:
                pass

        threading.Thread(target=_detect, daemon=True).start()

    def _apply_drive_type(self, dt: str):
        """Called on the main thread when background detection finishes."""
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        if dt == "SSD":
            self._dt_label.configure(text="SSD / NVMe", text_color=("#1a7a40", "#4ade80"))
        elif dt == "HDD":
            self._dt_label.configure(text="HDD  ⚠", text_color=YELLOW)
            self._hdd_warn.pack(anchor="w", padx=14, pady=(0, 2))
        else:
            self._dt_label.configure(text="Unknown", text_color=MUTED)

    def _tick_countdown(self):
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        if self._countdown > 0:
            if self._proceed_btn:
                self._proceed_btn.configure(
                    text=f"▶  START NOW  (auto in {self._countdown}s)")
            self._countdown -= 1
            self._auto_timer = self.after(1000, self._tick_countdown)
        else:
            self._ok()

    def _ok(self):
        if self._auto_timer:
            try:
                self.after_cancel(self._auto_timer)
            except Exception:
                pass
        self.proceed = True
        self.destroy()

    def _cancel(self):
        if self._auto_timer:
            try:
                self.after_cancel(self._auto_timer)
            except Exception:
                pass
        self.proceed = False
        self.destroy()


# ─── Export Diagnostic Package ─────────────────────────────────────────────────

def export_diagnostic_zip(last_cmd: str = "", extra_info: str = "") -> Path | None:
    ensure_app_dir()
    zip_path = APP_DIR / f"diagnostic_{time.strftime('%Y%m%d_%H%M%S')}.zip"
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if RAW_LOG_FILE.exists():
                zf.write(RAW_LOG_FILE, "raw.log")
            if SETTINGS_FILE.exists():
                zf.write(SETTINGS_FILE, "settings.json")
            if FINAL_REPORT_FILE.exists():
                zf.write(FINAL_REPORT_FILE, "last_result_report.txt")
            def _drive_info(p: str) -> str:
                if not p:
                    return "—"
                try:
                    pp = Path(p)
                    return (f"{get_filesystem_type(pp)} | "
                            f"{get_drive_type(pp)} | "
                            f"Free: {format_size(get_free_space(pp))}")
                except Exception:
                    return "—"

            temp_p  = ""
            out_p   = ""
            try:
                s = json.loads(SETTINGS_FILE.read_text()) if SETTINGS_FILE.exists() else {}
                temp_p = s.get("temp_folder", "")
                out_p  = s.get("output_folder", "")
            except Exception:
                pass

            session_info = "\n".join([
                f"PS5 FFPFSC PRO {APP_VERSION}",
                f"Generated:      {now_datetime()}",
                f"Python:         {sys.version}",
                f"OS:             {sys.platform} {os.name}",
                "",
                f"Last Command:   {last_cmd}",
                "",
                f"Temp Folder:    {temp_p or '—'}",
                f"Temp Drive:     {_drive_info(temp_p)}",
                f"Output Folder:  {out_p or '—'}",
                f"Output Drive:   {_drive_info(out_p)}",
                "",
                extra_info,
            ])
            zf.writestr("session_info.txt", session_info)
        return zip_path
    except Exception:
        return None


# ─── Settings Window ──────────────────────────────────────────────────────────

class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent_widget, app):
        super().__init__(parent_widget)
        self.app = app
        self.title(f"{APP_NAME} — Settings")
        self.geometry("600x680")
        self.resizable(False, True)
        self.grab_set()
        self.configure(fg_color=BLACK)
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="Settings",
                      font=ctk.CTkFont(size=24, weight="bold"), text_color=WHITE).pack(anchor="w", padx=20, pady=(20, 2))
        ctk.CTkLabel(self, text="Changes apply immediately.", text_color=MUTED).pack(anchor="w", padx=20, pady=(0, 12))

        scroll = ctk.CTkScrollableFrame(self, fg_color=BLACK)
        scroll.pack(fill="both", expand=True, padx=20, pady=(0, 8))

        # FOLDERS
        self._section_label(scroll, "FOLDERS")
        fold = ctk.CTkFrame(scroll, fg_color=PANEL, corner_radius=8)
        fold.pack(fill="x", pady=(4, 12))
        fold.grid_columnconfigure(1, weight=1)
        for row_i, (lbl, var, key, title) in enumerate([
            ("Default Output Folder", self.app.output_var, "output_folder", "Select Output Folder"),
            ("Default Temp Folder",   self.app.temp_var,   "temp_folder",   "Select Temp Folder"),
        ]):
            ctk.CTkLabel(fold, text=lbl + ":", text_color=MUTED, anchor="w", width=170).grid(
                row=row_i, column=0, padx=14, pady=8, sticky="w")
            ctk.CTkEntry(fold, textvariable=var, fg_color=CARD, border_color=BORDER2,
                          text_color=WHITE).grid(row=row_i, column=1, sticky="ew", padx=(0, 8), pady=8)
            ctk.CTkButton(fold, text="Browse", width=80, fg_color=CARD2, text_color=WHITE,
                           hover_color=("#b0b0b0", "#2a2a2a"),
                           command=lambda v=var, k=key, t=title: self._browse_folder(v, k, t)).grid(
                row=row_i, column=2, padx=(0, 14), pady=8)

        # COMPRESSION
        self._section_label(scroll, "COMPRESSION")
        comp = ctk.CTkFrame(scroll, fg_color=PANEL, corner_radius=8)
        comp.pack(fill="x", pady=(4, 12))
        for text, var, key in [
            ("Keep intermediate PFS image",           self.app.keep_pfs_var,        None),
            ("Verify output (slower, uses more RAM)", self.app.verify_output_var,    None),
            ("Auto-clear temp folder after success",  self.app.auto_clear_temp_var,  "auto_clear_temp"),
            ("Verbose mkpfs output (debug)",          self.app.verbose_var,           None),
        ]:
            cb = ctk.CTkCheckBox(comp, text=text, variable=var, fg_color=GREEN,
                                  hover_color=GREEN2, text_color=WHITE)
            if key:
                cb.configure(command=lambda k=key, v=var: save_settings({k: v.get()}))
            cb.pack(anchor="w", padx=14, pady=6)

        # MkPFS tuning sliders
        _st = ctk.CTkFrame(comp, fg_color="transparent")
        _st.pack(fill="x", padx=14, pady=(4, 8))
        _st.columnconfigure(1, weight=1)

        ctk.CTkLabel(_st, text="Compression level (0-9):", text_color=WHITE,
                      font=ctk.CTkFont(size=11)).grid(row=0, column=0, sticky="w", pady=4)
        ctk.CTkSlider(_st, from_=0, to=9, number_of_steps=9,
                       variable=self.app.compression_level_var,
                       fg_color=BORDER2, progress_color=GREEN, button_color=GREEN,
                       button_hover_color=GREEN2).grid(row=0, column=1, sticky="ew", padx=8, pady=4)
        _cl_lbl = ctk.CTkLabel(_st, text=str(self.app.compression_level_var.get()),
                                 text_color=GREEN, font=ctk.CTkFont(size=11, weight="bold"), width=24)
        _cl_lbl.grid(row=0, column=2)
        def _cl_cb(*_):
            v = self.app.compression_level_var.get()
            _cl_lbl.configure(text=str(v))
            save_settings({"compression_level": v})
        self.app.compression_level_var.trace_add("write", _cl_cb)

        ctk.CTkLabel(_st, text="CPU cores (0=auto):", text_color=WHITE,
                      font=ctk.CTkFont(size=11)).grid(row=1, column=0, sticky="w", pady=4)
        ctk.CTkSlider(_st, from_=0, to=16, number_of_steps=16,
                       variable=self.app.cpu_count_var,
                       fg_color=BORDER2, progress_color=GREEN, button_color=GREEN,
                       button_hover_color=GREEN2).grid(row=1, column=1, sticky="ew", padx=8, pady=4)
        _cpu_lbl = ctk.CTkLabel(_st, text="auto" if self.app.cpu_count_var.get() == 0 else str(self.app.cpu_count_var.get()),
                                  text_color=GREEN, font=ctk.CTkFont(size=11, weight="bold"), width=24)
        _cpu_lbl.grid(row=1, column=2)
        def _cpu_cb(*_):
            v = self.app.cpu_count_var.get()
            _cpu_lbl.configure(text="auto" if v == 0 else str(v))
            save_settings({"cpu_count": v})
        self.app.cpu_count_var.trace_add("write", _cpu_cb)

        ctk.CTkLabel(_st, text="Block size:", text_color=WHITE,
                      font=ctk.CTkFont(size=11)).grid(row=2, column=0, sticky="w", pady=4)
        _bs_opts = ["auto", "auto-fit", "65536", "32768", "16384"]
        _bs_menu = ctk.CTkOptionMenu(
            _st, values=_bs_opts, variable=self.app.block_size_var,
            fg_color=CARD2, button_color=GREEN, button_hover_color=GREEN2,
            text_color=WHITE, dropdown_fg_color=CARD2, dropdown_text_color=WHITE,
            dropdown_hover_color=GREEN, width=110, height=28,
            font=ctk.CTkFont(size=11),
            command=lambda v: save_settings({"block_size": v}),
        )
        _bs_menu.grid(row=2, column=1, sticky="w", padx=8, pady=4)
        ctk.CTkLabel(_st, text="auto=65536  auto-fit=minimise waste  16384/32768=small-file games",
                      text_color=MUTED, font=ctk.CTkFont(size=10)).grid(
            row=2, column=2, sticky="w", pady=4)

        ctk.CTkLabel(comp, text="Default Archive Password (optional):", text_color=MUTED, anchor="w").pack(
            anchor="w", padx=14, pady=(8, 2))
        ctk.CTkLabel(comp, text="Pre-fill the archive password field for password-protected ZIPs/RARs/7zs.",
                      text_color=MUTED, font=ctk.CTkFont(size=11), anchor="w").pack(
            anchor="w", padx=14)
        ctk.CTkEntry(comp, textvariable=self.app.password_var, show="*",
                      fg_color=CARD, border_color=BORDER2, text_color=WHITE).pack(
            fill="x", padx=14, pady=(4, 10))

        # USER INTERFACE
        self._section_label(scroll, "USER INTERFACE")
        ui = ctk.CTkFrame(scroll, fg_color=PANEL, corner_radius=8)
        ui.pack(fill="x", pady=(4, 12))
        for text, var in [
            ("Show summary popup when done", self.app.summary_popup_var),
            ("Play sound on completion",     self.app.sound_complete_var),
            ("Play sound on errors",         self.app.sound_error_var),
            ("Open output folder when done", self.app.open_output_var),
        ]:
            ctk.CTkCheckBox(ui, text=text, variable=var, fg_color=GREEN,
                             hover_color=GREEN2, text_color=WHITE).pack(anchor="w", padx=14, pady=6)
        theme_row = ctk.CTkFrame(ui, fg_color=PANEL)
        theme_row.pack(fill="x", padx=14, pady=(4, 10))
        ctk.CTkLabel(theme_row, text="Theme:", text_color=WHITE).pack(side="left", padx=(0, 10))
        ctk.CTkButton(theme_row, text="Toggle Dark / Light", fg_color=CARD2, text_color=WHITE,
                       hover_color=("#b0b0b0", "#2a2a2a"), width=160, command=self.app._toggle_theme).pack(side="left")

        # ABOUT
        self._section_label(scroll, "ABOUT")
        about = ctk.CTkFrame(scroll, fg_color=PANEL, corner_radius=8)
        about.pack(fill="x", pady=(4, 12))
        for line in [
            f"Version:  {APP_VERSION}",
            f"Backend:  {BACKEND_NAME}",
            f"MkPFS:    {MKPFS_NAME} v{MKPFS_VERSION}",
            f"Config:   {SETTINGS_FILE}",
            f"History:  {HISTORY_FILE}",
            f"Log:      {RAW_LOG_FILE}",
        ]:
            ctk.CTkLabel(about, text=line, text_color=MUTED, anchor="w",
                          font=ctk.CTkFont(family="Consolas", size=11)).pack(anchor="w", padx=14, pady=3)

        # Bottom buttons
        btns = ctk.CTkFrame(self, fg_color=BLACK)
        btns.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkButton(btns, text="Close", fg_color=GREEN, text_color="#061006",
                       hover_color=GREEN2, command=self.destroy).pack(side="right")
        ctk.CTkButton(btns, text="Open Config Folder", fg_color=CARD2, text_color=WHITE,
                       hover_color=("#b0b0b0", "#2a2a2a"),
                       command=lambda: open_path(APP_DIR)).pack(side="left")

    def _section_label(self, parent, text):
        ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=12, weight="bold"),
                      text_color=("#1a7a40", "#4ade80")).pack(anchor="w", pady=(10, 4))

    def _browse_folder(self, var, settings_key, title):
        p = filedialog.askdirectory(title=title)
        if p:
            var.set(p)
            save_settings({settings_key: p})


# ─── Archive Extractor ─────────────────────────────────────────────────────────

class ArchiveExtractor:
    """Extract ZIP / RAR / 7z to a temp subfolder and return the game root Path.

    Libraries used (all optional — falls back to CLI tools if missing):
      • ZIP  — zipfile (stdlib, always available)
      • RAR  — rarfile  (pip install rarfile)
      • 7z   — py7zr    (pip install py7zr)  or  7z / 7za CLI on PATH
    """

    SUPPORTED = {".zip", ".rar", ".7z"}

    @staticmethod
    def extract(archive: Path, dest_root: Path, log_fn=None, progress_fn=None,
                password: str = "") -> Path:
        """Extract *archive* under *dest_root/<stem>* and return the extracted root.
        progress_fn(pct, filename) is called periodically.
        password is used for encrypted archives (ZIP/RAR/7z)."""
        dest = dest_root / archive.stem
        dest.mkdir(parents=True, exist_ok=True)
        suffix = archive.suffix.lower()
        if log_fn:
            log_fn("INFO", f"Extracting {archive.name} → {dest}"
                   + (" [password-protected]" if password else ""))
        if suffix == ".zip":
            ArchiveExtractor._zip(archive, dest, log_fn, progress_fn, password)
        elif suffix == ".rar":
            ArchiveExtractor._rar(archive, dest, log_fn, progress_fn, password)
        elif suffix == ".7z":
            ArchiveExtractor._sevenz(archive, dest, log_fn, progress_fn, password)
        else:
            raise ValueError(f"Unsupported archive format: {archive.suffix}")
        game_root = ArchiveExtractor._find_root(dest)
        if log_fn:
            log_fn("OK", f"Extracted to: {game_root}")
        return game_root

    # ── format handlers ────────────────────────────────────────────────────────

    @staticmethod
    def _zip(archive: Path, dest: Path, log_fn, progress_fn=None, password: str = ""):
        pwd_bytes = password.encode() if password else None
        with zipfile.ZipFile(archive, "r") as zf:
            names = zf.namelist()
            total = len(names)
            for i, name in enumerate(names):
                zf.extract(name, dest, pwd=pwd_bytes)
                pct = int((i + 1) / total * 100) if total else 0
                if progress_fn:
                    progress_fn(pct, name)
                elif log_fn and total > 0 and i % max(1, total // 20) == 0:
                    log_fn("INFO", f"  {pct}%  {name}")

    @staticmethod
    def _find_rar_tool(log_fn=None) -> str | None:
        """Return the first usable RAR-extraction executable found, or None."""
        import shutil as _shutil

        _script_dir = Path(getattr(sys, "frozen", None) and sys.executable
                           or __file__).parent

        # Absolute-path candidates (check existence directly — no subprocess needed)
        absolute_candidates = [
            # Next to the app / in app-data (user can drop UnRAR.exe here)
            _script_dir / "unrar.exe",
            _script_dir / "tools" / "unrar.exe",
            APP_DIR / "unrar.exe",
            # 7-Zip standard install locations
            Path(r"C:\Program Files\7-Zip\7z.exe"),
            Path(r"C:\Program Files (x86)\7-Zip\7z.exe"),
            # WinRAR standard install locations
            Path(r"C:\Program Files\WinRAR\UnRAR.exe"),
            Path(r"C:\Program Files\WinRAR\Rar.exe"),
            Path(r"C:\Program Files (x86)\WinRAR\UnRAR.exe"),
            Path(r"C:\Program Files (x86)\WinRAR\Rar.exe"),
        ]
        for p in absolute_candidates:
            if p.exists():
                if log_fn:
                    log_fn("INFO", f"RAR tool found: {p}")
                return str(p)

        # Short names resolved via PATH
        for name in ("unrar", "rar", "7z", "7za"):
            if _shutil.which(name):
                if log_fn:
                    log_fn("INFO", f"RAR tool found on PATH: {name}")
                return name

        return None

    @staticmethod
    def _rar(archive: Path, dest: Path, log_fn, progress_fn=None, password: str = ""):
        # ── Try rarfile Python library first ──────────────────────────────────
        try:
            import rarfile  # type: ignore
            with rarfile.RarFile(str(archive)) as rf:
                if password:
                    rf.setpassword(password.encode())
                rf.extractall(str(dest))
            if log_fn:
                log_fn("OK", "RAR extracted via rarfile library")
            return
        except ImportError:
            pass
        except Exception as e:
            if log_fn:
                log_fn("WARN", f"rarfile failed ({e}) — trying CLI tools…")

        # ── Find any suitable CLI tool ─────────────────────────────────────────
        tool = ArchiveExtractor._find_rar_tool(log_fn=log_fn)
        if tool:
            tool_name = Path(tool).name.lower()
            is_7z = "7z" in tool_name
            if is_7z:
                # -bsp1 streams progress to stdout; -y auto-confirms
                cmd = [tool, "x", str(archive), f"-o{dest}", "-y", "-bsp1", "-bso0"]
                if password:
                    cmd.append(f"-p{password}")
            else:
                cmd = [tool, "x", "-y"]
                if password:
                    cmd.append(f"-p{password}")
                cmd += [str(archive), str(dest) + os.sep]

            if log_fn:
                log_fn("INFO", f"Running: {Path(tool).name}  (this may take a while for large archives…)")

            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                last_log_t = time.time()
                for line in proc.stdout or []:
                    line = line.rstrip()
                    if not line:
                        continue
                    # 7z progress lines look like "  3% - filename" — log every 5 s
                    if log_fn and (time.time() - last_log_t >= 5 or "error" in line.lower()):
                        log_fn("INFO", f"  extract: {line}")
                        last_log_t = time.time()
                    if progress_fn:
                        m = re.search(r"(\d+)%", line)
                        if m:
                            progress_fn(int(m.group(1)), line)
                code = proc.wait()
                if code != 0:
                    raise RuntimeError(f"{Path(tool).name} exited with code {code} — extraction failed.")
                if log_fn:
                    log_fn("OK", f"RAR extracted via {Path(tool).name}")
                return
            except RuntimeError:
                raise
            except Exception as e:
                raise RuntimeError(f"Extraction error ({Path(tool).name}): {e}")

        # ── Nothing worked — helpful error ─────────────────────────────────────
        _script_dir = Path(getattr(sys, "frozen", None) and sys.executable or __file__).parent
        raise RuntimeError(
            "Cannot extract RAR — no suitable tool found.\n\n"
            "EASIEST FIX — any ONE of these works:\n"
            "  1. Install 7-Zip:  https://www.7-zip.org/\n"
            "  2. Install WinRAR:  https://www.rarlab.com/download.htm\n"
            f" 3. Download UnRAR.exe from rarlab.com and drop it here:\n"
            f"       {_script_dir}\n\n"
            "ZIP and .7z archives extract without any extra tools."
        )

    @staticmethod
    def _sevenz(archive: Path, dest: Path, log_fn, progress_fn=None, password: str = ""):
        try:
            import py7zr  # type: ignore
            kwargs = {}
            if password:
                kwargs["password"] = password
            with py7zr.SevenZipFile(str(archive), mode="r", **kwargs) as sz:
                sz.extractall(str(dest))
            return
        except ImportError:
            pass
        # Fallback: 7z / 7za CLI
        for exe in ("7z", "7za"):
            try:
                cmd = [exe, "x", str(archive), f"-o{dest}", "-y"]
                if password:
                    cmd.append(f"-p{password}")
                subprocess.run(cmd, check=True,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except (FileNotFoundError, subprocess.CalledProcessError):
                pass
        raise RuntimeError(
            "Cannot extract 7z — install py7zr:  pip install py7zr\n"
            "or put 7z.exe on your PATH."
        )

    # ── helper ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _find_root(dest: Path) -> Path:
        """Walk the extraction tree and return the PS5 game root.

        Priority order:
          1. Any folder that directly contains sce_sys/param.json  (definitive)
          2. Any folder whose name matches a PS5 title-ID pattern  (PPSA/CUSA + 5 digits)
          3. Single top-level folder unwrap (one level, legacy behaviour)
          4. The dest itself as fallback
        """
        # BFS — check up to 4 levels deep so deeply nested archives still work
        from collections import deque
        queue_dirs: deque[Path] = deque([dest])
        visited = 0
        while queue_dirs and visited < 200:
            current = queue_dirs.popleft()
            visited += 1
            # Definitive PS5 game root marker
            if (current / "sce_sys" / "param.json").exists():
                return current
            try:
                subdirs = [p for p in current.iterdir() if p.is_dir()]
            except PermissionError:
                continue
            queue_dirs.extend(subdirs)

        # Second pass — title-ID folder name (e.g. PPSA14002-app, CUSA12345)
        queue_dirs = deque([dest])
        visited = 0
        while queue_dirs and visited < 200:
            current = queue_dirs.popleft()
            visited += 1
            if re.search(r'\b(?:PPSA|CUSA)\d{5}\b', current.name, re.I):
                return current
            try:
                queue_dirs.extend(p for p in current.iterdir() if p.is_dir())
            except PermissionError:
                continue

        # Legacy: single top-level folder unwrap
        try:
            items = [p for p in dest.iterdir() if p.is_dir()]
            if len(items) == 1:
                return items[0]
        except Exception:
            pass

        return dest


# ─── Game Item ─────────────────────────────────────────────────────────────────

class GameItem:
    def __init__(self, path: Path):
        self.path       = path
        self.archive_path: Path | None = None   # set for archive placeholders
        self.name       = guess_game_name(path)
        self.title_id   = parse_title_id(path)
        self.size       = folder_size(path)
        self.files      = file_count(path)
        self.artwork    = find_artwork(path)
        self.status     = "Queued"

    @classmethod
    def from_archive(cls, archive: Path) -> "GameItem":
        """Placeholder item for an archive that has not been extracted yet."""
        obj          = cls.__new__(cls)
        obj.path         = None
        obj.archive_path = archive
        obj.name         = archive.stem
        obj.title_id     = "📦"
        obj.size         = archive.stat().st_size if archive.exists() else 0
        obj.files        = 0
        obj.artwork      = None
        obj.status       = "Pending Extract"
        return obj

    @classmethod
    def from_exfat(cls, exfat_file: Path) -> "GameItem":
        """Item for a direct .exfat / .ffpkg disk image — passed straight to cli.py, no extraction needed."""
        obj              = cls.__new__(cls)
        obj.path         = exfat_file          # handed directly to the backend
        obj.archive_path = None                # not an archive — no extraction step
        obj.name         = exfat_file.stem
        obj.title_id     = parse_title_id(exfat_file) or "💾"
        obj.size         = exfat_file.stat().st_size if exfat_file.exists() else 0
        obj.files        = 1
        obj.artwork      = None
        obj.status       = "Queued"
        return obj


# ─── CLI Worker ────────────────────────────────────────────────────────────────

class CLIWorker(threading.Thread):
    WEIGHTS = {
        "Scanning Files":      (0,    8),
        "Reading Game":        (8,   18),
        "Creating Temp PFS":   (18,  40),
        "Compressing":         (40,  80),
        "Writing Final Image": (80,  93),
        "Verifying Output":    (93,  97),
        "Cleaning Up":         (97, 100),
        "Complete":            (100, 100),
    }

    def __init__(self, app, item, cmd, cwd, output_dir, temp_dir):
        super().__init__(daemon=True)
        self.app = app
        self.item = item
        self.cmd = cmd
        self.cwd = cwd
        self.output_dir = output_dir
        self.temp_dir = temp_dir
        self.proc = None
        self.start_time = 0
        self.last_heartbeat = 0
        self.last_log = 0
        self.last_status_ui = 0
        self.last_log_ui = 0
        self.phase = "Starting"
        self.output_path = ""
        self.final_size = 0
        self.speed = "—"
        self.temp_start_size = get_folder_size(self.temp_dir)
        self.temp_peak_size = self.temp_start_size
        self.last_cmd_str = " ".join(cmd)
        self.stage_progress = {
            "Scanning Files": 0,
            "Reading Game": 0,
            "Creating Temp PFS": 0,
            "Compressing": 0,
            "Writing Final Image": 0,
            "Verifying Output": 0,
            "Cleaning Up": 0,
            "Complete": 0,
        }
        self.last_stage_bucket = {}
        self._mem_error_shown = False   # reset per-job so next run can show it again

    def run(self):
        ensure_app_dir()
        self.start_time = time.time()
        self.last_heartbeat = self.start_time

        # Raw log strategy: rolling tail buffer.
        # All backend lines are held in a deque; error lines are always kept in a
        # separate list so they are never dropped.  At job end the last 10 MB of
        # regular output + all errors are written to disk.
        RAW_LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB tail window
        from collections import deque as _deque
        _raw_lines: _deque[str] = _deque()   # rolling ring buffer (all lines)
        _raw_errors: list[str]  = []          # every ERROR/FAILED line (always kept)
        _raw_buf_bytes          = 0           # current byte count in _raw_lines

        def _raw_append(text: str):
            nonlocal _raw_buf_bytes
            encoded = text.encode("utf-8", errors="replace")
            _raw_lines.append(text)
            _raw_buf_bytes += len(encoded)
            # Keep last 10 MB — drop oldest lines from the front
            while _raw_buf_bytes > RAW_LOG_MAX_BYTES and _raw_lines:
                dropped = _raw_lines.popleft()
                _raw_buf_bytes -= len(dropped.encode("utf-8", errors="replace"))

        self.app.log("INFO", f"{APP_NAME} {APP_VERSION} started")
        self.app.log("INFO", f"Backend: {BACKEND_NAME}")
        self.app.log("INFO", f"MkPFS: {MKPFS_NAME} v{MKPFS_VERSION}")
        self.app.log("INFO", f"Game: {self.item.title_id} | {self.item.name}")
        self.app.log("INFO", f"Original: {format_size(self.item.size)} | Files: {self.item.files}")
        self.app.log("INFO", f"Backend Python: {' '.join(get_backend_python_command()) or 'NOT FOUND'}")
        self.app.log("CMD", self.last_cmd_str)
        _raw_append("[COMMAND] " + self.last_cmd_str + "\n")

        try:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            self.temp_dir.mkdir(parents=True, exist_ok=True)
            env["TEMP"] = str(self.temp_dir)
            env["TMP"] = str(self.temp_dir)
            env["TMPDIR"] = str(self.temp_dir)

            self.proc = subprocess.Popen(
                self.cmd,
                cwd=str(self.cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                universal_newlines=True,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self.app.current_process = self.proc

            # ── Define flush helper (used periodically during run AND at end) ─
            _last_flush_t = time.time()
            FLUSH_INTERVAL = 30  # write raw log to disk every ~30 s during the run

            def _flush_raw_log():
                try:
                    RAW_LOG_FILE.unlink(missing_ok=True)
                except Exception:
                    pass
                try:
                    with RAW_LOG_FILE.open("w", encoding="utf-8", errors="replace") as f:
                        if _raw_errors:
                            f.write("=" * 60 + "\n")
                            f.write("ERRORS / FAILURES ENCOUNTERED DURING THIS JOB\n")
                            f.write("=" * 60 + "\n")
                            f.writelines(_raw_errors)
                            f.write("=" * 60 + "\n\n")
                        f.write(f"[LAST {RAW_LOG_MAX_BYTES // (1024*1024)} MB OF BACKEND OUTPUT]\n\n")
                        f.writelines(_raw_lines)
                except Exception:
                    pass

            # ── Read backend output line by line ──────────────────────────────
            for line in self.proc.stdout or []:
                if self.app.cancel_requested:
                    self._terminate()
                    break

                clean = line.rstrip("\r\n")
                _raw_append(clean + "\n")
                # Always collect error lines separately so they survive the tail trim
                upper_c = clean.upper()
                if re.search(r'\bERROR\b|\bFAILED\b', upper_c):
                    _raw_errors.append(clean + "\n")
                self._handle_line(clean)

                t = time.time()
                if t - self.last_heartbeat >= 30:
                    self.last_heartbeat = t
                    elapsed = format_duration(t - self.start_time)
                    self.app.status_update("Still Working", "Backend is active. Do not close the app.", self.phase, self.stage_progress.get(self.phase, 0), self._overall(), elapsed, self.speed, "—")
                    self.app.log("HEARTBEAT", f"Still working | Stage: {self.phase} | Elapsed: {elapsed}")

                # Periodic flush so the log file exists while the job is running
                if t - _last_flush_t >= FLUSH_INTERVAL:
                    _flush_raw_log()
                    _last_flush_t = t

            # ── stdout fully consumed — now wait for process to exit ───────────
            code = self.proc.wait() if self.proc else 1

            # ── Final flush of rolling log buffer ─────────────────────────────
            _flush_raw_log()

            if self.app.cancel_requested:
                self.app.finish(False, "Cancelled by user.", self.last_cmd_str)
                return
            if code != 0:
                smart = smart_error_from_log()
                msg = smart if smart else f"Backend exited with code {code}."
                self.app.finish(False, msg, self.last_cmd_str)
                return

            self._set_stage("Cleaning Up", 100, "Temporary cleanup finished.")
            try:
                self.temp_peak_size = max(self.temp_peak_size, get_folder_size(self.temp_dir))
            except Exception:
                pass
            if not self._find_output():
                self._write_report(False)
                self.app.finish(False, "Backend exited but no new .ffpfsc output was created.", self.last_cmd_str)
                return
            # ShadowMount compatibility checks
            for w in self._validate_shadowmount():
                self.app.log("WARN", w)
            self._write_report(True)
            self.app.add_history(self.item, self.output_path, self.final_size, time.time() - self.start_time)
            self.app.finish(True, "Compression completed successfully.", self.last_cmd_str)
        except Exception as e:
            try:
                _raw_append(f"[GUI ERROR] {e}\n")
                _flush_raw_log()
            except Exception:
                pass
            self.app.finish(False, str(e), self.last_cmd_str)
        finally:
            self.app.current_process = None

    def _stage_from_label(self, label: str, raw: str) -> str | None:
        """Return the stage name inferred from a progress-bar label, or None if uncertain.

        Returning None means the caller should NOT update the stage — the line
        didn't contain enough signal to be confident about which stage we're in.
        This prevents unrecognised lines from locking the display on the current stage.
        """
        text = f"{label} {raw}".lower()  # full combined text for substring checks

        # The backend progress-bar label is everything after the "%" —
        #   "[###] 65% compress @ 290.95 MB/s ETA 14s"  → label = "compress @ 290.95 MB/s ETA 14s"
        #   "[###] 45% write @ 980.61 MB/s ETA 0s"      → label = "write @ 980.61 MB/s ETA 0s"
        #   "[###]  2% scan"                             → label = "scan"
        # Use the FIRST WORD of the label for reliable matching regardless of trailing speed/ETA.
        first_word = label.strip().lower().split()[0] if label.strip() else ""

        # ── Final output ──────────────────────────────────────────────────────
        # Check before generic "write" so ".ffpfsc" always wins
        if ".ffpfsc" in text or "final image" in text or "final output" in text:
            return "Writing Final Image"

        # ── Backend label "write" ─────────────────────────────────────────────
        # Emitted during temp-PFS construction (before compress) AND final image write (after).
        # Distinguish by whether compression has started yet.
        if first_word in ("write", "writing"):
            if self.stage_progress.get("Compressing", 0) > 0:
                return "Writing Final Image"
            else:
                return "Creating Temp PFS"

        # ── Scan / discovery ──────────────────────────────────────────────────
        if first_word in ("scan", "scanning") or "discover" in text:
            return "Scanning Files"

        # ── Reading game files ────────────────────────────────────────────────
        if first_word in ("read", "reading"):
            return "Reading Game"

        # ── Compression ───────────────────────────────────────────────────────
        if first_word in ("compress", "compressing") or "compress" in text:
            return "Compressing"

        # ── Verify (only from a real progress bar, not plain-text messages) ───
        if first_word in ("verify", "verifying"):
            return "Verifying Output"

        # ── Looser substring fallbacks for non-standard backend messages ──────
        if "scan" in text or "discover" in text:
            return "Scanning Files"
        if "read" in text and "write" not in text:
            return "Reading Game"
        if "clean" in text or "delete" in text or "removed" in text:
            return "Cleaning Up"

        # "Complete" is NEVER returned here — set only by run() after exit.
        # Returning None means: "uncertain — don't change the stage display."
        return None

    def _overall_for_stage(self, stage: str, pct: float) -> float:
        start, end = self.WEIGHTS.get(stage, (0, 100))
        return max(0, min(100, start + (max(0, min(100, pct)) / 100) * (end - start)))

    def _overall(self):
        return self._overall_for_stage(self.phase, self.stage_progress.get(self.phase, 0))

    # Ordered list used to prevent backward stage transitions.
    # Must be a plain tuple/list literal here — _STAGE_DEFS is defined later in
    # the module (after CLIWorker), so we can't reference it at class-body time.
    _STAGE_ORDER = [
        "Scanning Files", "Reading Game", "Creating Temp PFS",
        "Compressing", "Writing Final Image", "Verifying Output",
        "Cleaning Up", "Complete",
    ]

    def _set_stage(self, stage, pct, label="", eta="—", force=False):
        # Never allow the stage to regress (e.g. backend prints "Writing PFS image"
        # after compression has already started — that would snap back to Temp PFS).
        if not force and stage in self._STAGE_ORDER and self.phase in self._STAGE_ORDER:
            if self._STAGE_ORDER.index(stage) < self._STAGE_ORDER.index(self.phase):
                return
        self.phase = stage
        pct = max(0, min(100, pct))
        if stage == "Creating Temp PFS" and pct >= 100:
            pct = 99
        self.stage_progress[stage] = max(self.stage_progress.get(stage, 0), pct)

        # When a later stage begins, snap earlier stages to 100% so the
        # breadcrumbs never show a stale partial % (e.g. "Temp PFS 5%").
        # This handles backends that stop emitting progress before 100%.
        if stage == "Compressing":
            self.stage_progress["Creating Temp PFS"] = 100
            self.stage_progress["Reading Game"]       = 100
        elif stage == "Writing Final Image":
            self.stage_progress["Creating Temp PFS"] = 100
            self.stage_progress["Compressing"]        = 100
        elif stage == "Verifying Output":
            self.stage_progress["Writing Final Image"] = 100
            self.stage_progress["Compressing"]         = 100
        elif stage in ("Cleaning Up", "Complete"):
            for s in ("Scanning Files", "Reading Game", "Creating Temp PFS",
                      "Compressing", "Writing Final Image"):
                if self.stage_progress.get(s, 0) > 0:
                    self.stage_progress[s] = 100

        elapsed = format_duration(time.time() - self.start_time)
        overall = self._overall_for_stage(stage, self.stage_progress[stage])

        detail = label or f"{stage} is active."
        if stage == "Creating Temp PFS":
            detail = ("Building temporary PFS image. "
                      "Large games may look frozen here — the backend is still working. "
                      "Do NOT close the app.")
        elif stage == "Cleaning Up":
            detail = "Cleaning up temporary files. Please wait before closing the app."
        elif stage == "Writing Final Image":
            # Backend writes the final .ffpfsc silently (no progress bars) — the display
            # may show 0% for a while then snap to 100% when the write finishes.
            detail = ("Writing the final .ffpfsc output file. "
                      "This stage may show 0% — the backend is writing silently. "
                      "Do NOT close the app.")
        elif stage == "Compressing" and not label:
            detail = "Compressing game data."

        now = time.time()
        bucket = (int(self.stage_progress[stage]) // 5) * 5
        should_update_ui = (force
                            or (now - self.last_status_ui >= 0.5)
                            or self.last_stage_bucket.get(stage, -1) != bucket
                            or int(self.stage_progress[stage]) == 100)
        if should_update_ui:
            self.last_status_ui = now
            self.app.status_update(stage, detail, stage, self.stage_progress[stage],
                                   overall, elapsed, self.speed, eta)

        # Only log at 5 % bucket boundaries or when a stage hits 100 %.
        # Do NOT log at 0 % on every bar — that floods the log when the backend
        # emits dozens of 0 % lines before the first real progress tick.
        if self.last_stage_bucket.get(stage, -1) != bucket or int(self.stage_progress[stage]) == 100:
            self.last_stage_bucket[stage] = bucket
            self.app.log("PROGRESS", f"{stage}: {int(self.stage_progress[stage])}% {label}".strip())

    def _handle_line(self, line):
        if not line:
            return

        lower = line.lower()
        upper = line.upper()

        # ── Intercept raw Python exception tracebacks from the backend ────────
        # Convert confusing Python tracebacks into readable, actionable messages
        # and always include UI settings suggestions the user can act on right now.

        # MemoryError — mkpfs multiprocessing pool ran out of RAM.
        # Each parallel worker loads a chunk of the source file; too many cores = OOM.
        # Only match raw Python exception lines (no leading '[' bracket like [INFO]/[OK]).
        # This avoids false-positives from mkpfs info messages that mention "MemoryError".
        # Only show once per job to avoid log spam.
        stripped = line.strip()
        if (stripped == "MemoryError"
                or ("memoryerror" in lower and not stripped.startswith("[") and "avoid" not in lower)):
            if not getattr(self, "_mem_error_shown", False):
                self._mem_error_shown = True
                self.app.log("ERROR",
                    "❌  Out of RAM — mkpfs ran out of memory during parallel compression.\n"
                    "\n"
                    "  What happened:\n"
                    "    mkpfs spawns one worker process per CPU core. Each worker holds\n"
                    "    compressed data in RAM. Too many cores = not enough memory.\n"
                    "\n"
                    "  ╔═ Try these settings (Compression Tuning bar): ══════════════╗\n"
                    "  ║  CPU cores  →  set to 2 (or 1 for very large games)         ║\n"
                    "  ║  Level      →  try 5 instead of 7 (less RAM per worker)     ║\n"
                    "  ║  Block size →  try 16384 or 32768 (smaller per-block buffers) ║\n"
                    "  ╚═══════════════════════════════════════════════════════════════╝"
                )
            return

        # Downstream noise caused by the MemoryError — suppress silently.
        if "concurrent send_bytes" in lower or "maybeencodingerror" in lower:
            return

        # OSError [Errno 22] Invalid argument on write.
        # Either the output drive is exFAT/FAT32 (4 GB file limit) or a corrupt
        # chunk was written after an OOM crash.
        if ("oserror" in lower or "ioerror" in lower) and (
            "errno 22" in lower or "invalid argument" in lower
        ):
            self.app.log("ERROR",
                "❌  Write failed — OS error 22 (Invalid argument).\n"
                "\n"
                "  Most likely cause:  output drive is exFAT or FAT32\n"
                "    exFAT / FAT32 has a 4 GB per-file limit.\n"
                "    A large .ffpfsc will exceed this and fail mid-write.\n"
                "\n"
                "  ╔═ Settings to check / change: ═══════════════════════════════╗\n"
                "  ║  OUTPUT folder  →  move to an NTFS drive (e.g. C:\\  D:\\)   ║\n"
                "  ║  CPU cores      →  set to 1–2 if RAM could also be the cause ║\n"
                "  ╚══════════════════════════════════════════════════════════════╝"
            )
            return

        # No-space-left / disk full
        if ("errno 28" in lower or "no space left" in lower
                or "there is not enough space" in lower):
            self.app.log("ERROR",
                "❌  Disk full — the output or temp drive ran out of space.\n"
                "\n"
                "  ╔═ Settings to check: ════════════════════════════════════════╗\n"
                "  ║  OUTPUT folder  →  point to a drive with more free space    ║\n"
                "  ║  TEMP folder    →  point to a drive with more free space    ║\n"
                "  ║                    (needs ~1.5× the game size during build) ║\n"
                "  ╚══════════════════════════════════════════════════════════════╝"
            )
            return

        if "calledprocesserror" in lower and "non-zero exit status" in lower:
            self.app.log("ERROR", "❌  mkpfs exited with an error — see messages above.")
            if not getattr(self, "_mem_error_shown", False):
                # Generic hint only when a more specific error wasn't already shown.
                self.app.log("ERROR",
                    "  Common causes & settings to try:\n"
                    "\n"
                    "  ╔═ Check these settings: ══════════════════════════════════════╗\n"
                    "  ║  OUTPUT folder  →  must be NTFS (not exFAT / FAT32)          ║\n"
                    "  ║  TEMP folder    →  needs ~1.5× game size of free space       ║\n"
                    "  ║  CPU cores      →  lower to 2 or 1 if you have limited RAM   ║\n"
                    "  ║  Level          →  try 5 if high level causes OOM            ║\n"
                    "  ╚═══════════════════════════════════════════════════════════════╝\n"
                    "  If mkpfs is missing:  pip install mkpfs\n"
                    "  Full error detail is in the raw log."
                )
            return

        if "Compression complete:" in line:
            self.output_path = line.split("Compression complete:", 1)[-1].strip()

        prog = PROGRESS_RE.search(line)
        if prog:
            pct = max(0, min(100, int(prog.group("pct"))))
            label = prog.group("label").strip()
            stage = self._stage_from_label(label, line)

            sp = re.search(r"@\s*([0-9.]+\s*(?:GB|MB)/s)", label, re.I)
            if sp:
                self.speed = sp.group(1)

            eta_match = re.search(r"ETA\s*([0-9]+\s*(?:s|m|h|sec|secs|seconds|min|mins|minutes)?)", label, re.I)
            eta = eta_match.group(1).strip() if eta_match else "—"

            if stage is None:
                # Unrecognised progress line — update speed/eta but don't change stage
                return

            if stage == "Reading Game" and pct >= 100:
                self._set_stage("Reading Game", 100, label, eta)
                self._set_stage("Creating Temp PFS", 0, "Building temporary PFS image. Do NOT close the app.", "—")
                return

            if stage == "Compressing" and pct >= 100:
                self._set_stage("Compressing", 100, label, eta)
                # Auto-advance: compression finished — final image write is next.
                # If the backend emits its own "write" progress bars for the final
                # output, they will continue updating "Writing Final Image" from here.
                # If it writes silently, this at least moves the display off "Compressing".
                self._set_stage("Writing Final Image", 0, "Writing final .ffpfsc output file…", "—")
                return

            self._set_stage(stage, pct, label, eta)
            return

        # Hardlink / symlink failure — warn immediately, don't wait for exit code
        if "unable to stage source file" in lower or "hard link and symlink both failed" in lower:
            self.app.log("WARN",
                "⚠  Temp drive does not support hardlinks/symlinks. "
                "Fallback to copy mode — compression will be slower and needs extra space.")

        # Inner image auto-rename (MkPFS 0.0.8) — informational, not an error
        if "renaming inner image" in lower or "inner image renamed" in lower:
            self.app.log("INFO",
                "ℹ  mkpfs renamed the inner image to match the outer filename. "
                "This is normal — the .ffpfsc will mount correctly.")

        # Plain-text (non-progress-bar) stage hints.
        # IMPORTANT: only use very specific phrases here — broad keyword matches on
        # paths (e.g. _ffpfsc_temp, pfs_image.dat) fire too early because those
        # strings appear in the parameter dump before scanning even begins.
        if "writing pfs image to" in lower:
            # Only the exact "Writing PFS image to <path>" line marks temp-PFS start.
            # Use 0% so the subsequent [###] x% write progress bars can own the percentage
            # cleanly (the max() guard in _set_stage would pin it at 5 otherwise).
            self._set_stage("Creating Temp PFS", 0, "Building PFS image…")
        elif ".ffpfsc" in lower and self.stage_progress.get("Compressing", 0) > 0:
            # A line mentioning the final .ffpfsc output after compression has run
            # means the final image is being written (or has just been written).
            self._set_stage("Writing Final Image",
                            max(5, self.stage_progress.get("Writing Final Image", 0)),
                            "Writing final .ffpfsc output file…")
        elif "successfully wrote" in lower or "pfs creation complete" in lower:
            # PFS image fully written — advance to Compressing if not already there
            if self.stage_progress.get("Compressing", 0) == 0:
                self._set_stage("Creating Temp PFS", 100, line)
        # NOTE: "Verifying Output" is NOT triggered from plain-text here because
        # lines like "MkPFS post-build verify is disabled..." contain "verify" and
        # would fire this stage at the very start of the run, blocking everything else.
        # Verification stage is advanced only by progress bars in _stage_from_label.
        # NOTE: "Complete" stage is intentionally NOT set here — only by run() after exit.

        tag = "INFO"
        # Use word-boundary regex so "MemoryError", "TypeError", etc. don't
        # falsely tag an INFO line as ERROR.
        if re.search(r'\bERROR\b|\bFAILED\b', upper):
            tag = "ERROR"
        elif re.search(r'\bWARN\b|\bWARNING\b', upper):
            tag = "WARN"
        elif "SUCCESS" in upper or "[OK]" in upper or "COMPLETE" in upper:
            tag = "OK"

        # Errors and warnings are ALWAYS shown — never throttled.
        always_show = tag in ("ERROR", "WARN")
        important = always_show or tag != "INFO" or any(k in upper for k in [
            "BUILD SUMMARY", "TOTAL FILES", "TOTAL UNCOMPRESSED", "TOTAL STORED",
            "INPUT PATH", "OUTPUT PATH", "ELAPSED", "THROUGHPUT",
            "DISCOVERING", "COMPRESSING", "WRITING", "VERIFY", "INSPECT"
        ])
        t = time.time()
        if important or t - self.last_log >= 3:
            if not always_show:
                self.last_log = t
            self.app.log(tag, line)

    def _find_output(self):
        if self.output_path:
            p = Path(self.output_path.strip('"'))
            try:
                if p.exists() and p.is_file() and p.stat().st_size > 0 and p.stat().st_mtime >= self.start_time - 2:
                    self.final_size = p.stat().st_size
                    return True
            except OSError:
                pass

        newest = find_newest_ffpfsc_after(self.output_dir, self.start_time)
        if newest:
            self.output_path = str(newest)
            self.final_size = newest.stat().st_size
            return True

        self.output_path = ""
        self.final_size = 0
        return False

    def _validate_shadowmount(self) -> list:
        """Post-compression ShadowMount compatibility checks.
        Returns a list of warning strings (empty = all OK)."""
        warns = []
        if not self.output_path:
            return ["No output path recorded — cannot validate output."]
        p = Path(self.output_path)
        if not p.exists():
            warns.append(f"Output file not found on disk: {p.name}")
            return warns
        name_lower = p.name.lower()
        if name_lower.endswith(".ffpfsc.ffpfsc"):
            warns.append(
                f"⚠ Double extension detected: {p.name}\n"
                "   Rename the file — remove one '.ffpfsc' suffix before mounting in ShadowMount."
            )
        elif not name_lower.endswith(".ffpfsc"):
            warns.append(
                f"⚠ Unexpected output extension '{p.suffix}' — expected .ffpfsc\n"
                "   ShadowMount may not recognise this file."
            )
        sz = p.stat().st_size
        if sz == 0:
            warns.append("⚠ Output file is 0 bytes — compression may have failed silently.")
        elif sz < 1 * 1024 * 1024:
            warns.append(
                f"⚠ Output file is very small ({format_size(sz)}) — "
                "the source dump may be incomplete or empty."
            )
        return warns

    def _write_report(self, success=True):
        if success:
            self._find_output()
        elapsed = time.time() - self.start_time
        saved = self.item.size - self.final_size if self.item.size and self.final_size else 0
        pct = (saved / self.item.size * 100) if self.item.size else 0
        rating, recommendation = compression_rating(pct)
        temp_removed = max(0, self.temp_peak_size - get_folder_size(self.temp_dir))
        FINAL_REPORT_FILE.write_text(
            f"{APP_NAME} Report\n\n"
            f"Status: {'Success' if success else 'Failed'}\n"
            f"Game: {self.item.name}\n"
            f"Title ID: {self.item.title_id}\n"
            f"Source: {self.item.path}\n"
            f"Output: {self.output_path or 'Unknown'}\n"
            f"Original Size: {format_size(self.item.size)}\n"
            f"Output Size: {format_size(self.final_size)}\n"
            f"Space Saved: {format_size(saved)} ({pct:.2f}%)\n"
            f"Compression Rating: {rating}\n"
            f"Recommendation: {recommendation}\n"
            f"Peak Temp Usage Seen: {format_size(self.temp_peak_size)}\n"
            f"Temporary Files Removed: {format_size(temp_removed)}\n"
            f"Elapsed: {format_duration(elapsed)}\n"
            f"Backend: {BACKEND_NAME}\n"
            f"MkPFS: {MKPFS_NAME} v{MKPFS_VERSION}\n",
            encoding="utf-8",
            errors="replace",
        )

    def _terminate(self):
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
        except Exception:
            pass


# Stage definitions: (full backend name, short display label)
_STAGE_DEFS = [
    ("Scanning Files",      "Scan"),
    ("Reading Game",        "Read"),
    ("Creating Temp PFS",   "Temp PFS"),
    ("Compressing",         "Compress"),
    ("Writing Final Image", "Write"),
    ("Verifying Output",    "Verify"),
    ("Cleaning Up",         "Cleanup"),
    ("Complete",            "Done"),
]

# ─── Main Application ──────────────────────────────────────────────────────────

class App:
    def __init__(self, root):
        self.root = root
        self.queue = []
        self.current_process = None
        self.cancel_requested = False
        self.pending_start = False
        self.worker = None
        self._last_cmd_str = ""
        self._theme = "dark"
        # Batch auto-advance tracking (Feature 4)
        self._batch_total   = 0
        self._batch_done    = 0
        self._batch_failed  = 0
        self._batch_running = False
        self._details_item  = None   # GameItem currently shown in the details panel
        self._settings_win  = None

        self.log_q      = queue.Queue()
        self.progress_q = queue.Queue()
        self.status_q   = queue.Queue()
        self.done_q     = queue.Queue()
        self.scan_q     = queue.Queue()
        self._extract_q = queue.Queue()   # archive extraction completion
        self.visible_log_lines = 0
        self.auto_scroll_logs = True

        self._setup()
        self._build()
        self._poll()

        if is_first_run():
            self.root.after(200, self._show_first_run_wizard)

        # After the UI is fully loaded, remind user to report any untested games
        self.root.after(4000, self._check_pending_compat_reports)

    def _setup(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.geometry("1400x960")
        self.root.minsize(1100, 760)

        settings = load_settings()
        self._saved_output = settings.get("output_folder", "")
        self._saved_temp = settings.get("temp_folder", "")
        self._saved_auto_clear_temp = settings.get("auto_clear_temp", False)
        self._saved_compression_level = settings.get("compression_level", 7)
        self._saved_cpu_count = settings.get("cpu_count", 0)
        self._saved_block_size = settings.get("block_size", "auto")

    def _show_first_run_wizard(self):
        wiz = FirstRunWizard(self.root)
        self.root.wait_window(wiz)
        if wiz.result.get("temp_folder"):
            self.temp_var.set(wiz.result["temp_folder"])
        if wiz.result.get("output_folder"):
            self.output_var.set(wiz.result["output_folder"])

    def panel(self, parent, **grid):
        frame = ctk.CTkFrame(parent, fg_color=PANEL, border_width=1, border_color=BORDER, corner_radius=10)
        frame.grid(**grid)
        return frame

    def _button(self, parent, text, command=None, green=False, red=False, yellow=False, **kw):
        if green:
            color, hover, txt = GREEN, GREEN2, "#061006"
        elif red:
            color, hover, txt = RED, ("#b91c1c", "#5a1a1a"), WHITE
        elif yellow:
            color, hover, txt = YELLOW, ("#a37c10", "#c9a00e"), "#061006"
        else:
            # Normal button: CARD2 fill, slightly darker hover in both modes
            color, hover, txt = CARD2, ("#b0b0b0", "#2a2a2a"), WHITE
        return ctk.CTkButton(parent, text=text, command=command, fg_color=color, hover_color=hover,
                              text_color=txt, border_width=0 if (green or red or yellow) else 1,
                              border_color=BORDER2, **kw)

    def _build(self):
        self.root.configure(fg_color=BLACK)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        main = ctk.CTkFrame(self.root, fg_color=BLACK, corner_radius=0)
        main.grid(row=0, column=0, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=2)       # content area — can shrink
        main.grid_rowconfigure(4, weight=1, minsize=220)  # log always visible

        # ── Header ──────────────────────────────────────────────────────────
        header = ctk.CTkFrame(main, fg_color=BLACK)
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 8))
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(header, text="PS5 FFPFSC PRO",
                      font=ctk.CTkFont(size=30, weight="bold"), text_color=WHITE).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(header, text=f"v{APP_VERSION}  •  Bizkut Backend  •  {MKPFS_NAME} v{MKPFS_VERSION}  •  by KINGDKAK",
                      text_color=MUTED).grid(row=1, column=0, sticky="w", padx=2)

        self.header_status_var = tk.StringVar(value=f"v{APP_VERSION}  |  Backend: Ready")
        ctk.CTkLabel(header, textvariable=self.header_status_var,
                      text_color=MUTED, font=ctk.CTkFont(size=14)).grid(row=0, column=2, padx=12)

        # START / CANCEL always visible in header
        self.start_btn = self._button(header, "▶  START QUEUE", self.start, green=True, width=150, height=36)
        self.start_btn.grid(row=0, column=3, rowspan=1, padx=(0, 6), pady=2, sticky="e")
        self.cancel_btn = self._button(header, "✕  CANCEL", self.cancel, red=True, width=120, height=36)
        self.cancel_btn.grid(row=0, column=4, padx=(0, 6), pady=2, sticky="e")
        self.cancel_btn.configure(state="disabled")

        self._button(header, "☀ Light / 🌙 Dark", self._toggle_theme, width=150).grid(row=1, column=2, padx=12, sticky="e")
        self._button(header, "⚙  Settings", self.open_settings, width=120).grid(row=1, column=3, columnspan=2, padx=(0, 4), sticky="e")

        # ── Variables ────────────────────────────────────────────────────────
        self.source_var = tk.StringVar()
        self.output_var = tk.StringVar(value=self._saved_output)
        self.temp_var = tk.StringVar(value=self._saved_temp)
        self.password_var = tk.StringVar()
        self.keep_pfs_var = tk.BooleanVar(value=False)
        self.open_output_var = tk.BooleanVar(value=False)
        self.summary_popup_var = tk.BooleanVar(value=True)
        self.sound_complete_var = tk.BooleanVar(value=True)
        self.sound_error_var = tk.BooleanVar(value=True)
        self.batch_var = tk.BooleanVar(value=False)
        self.verify_output_var = tk.BooleanVar(value=False)
        self.auto_clear_temp_var = tk.BooleanVar(value=self._saved_auto_clear_temp)
        # MkPFS 0.0.8 tuning
        self.compression_level_var = tk.IntVar(value=self._saved_compression_level)
        self.cpu_count_var         = tk.IntVar(value=self._saved_cpu_count)
        self.verbose_var           = tk.BooleanVar(value=False)
        self.block_size_var        = tk.StringVar(value=self._saved_block_size)

        # ── Top folder row ───────────────────────────────────────────────────
        top = self.panel(main, row=1, column=0, sticky="ew", padx=18, pady=8)
        top.grid_columnconfigure(1, weight=1)
        top.grid_columnconfigure(3, weight=1)
        top.grid_columnconfigure(5, weight=1)

        add_btns = ctk.CTkFrame(top, fg_color="transparent")
        add_btns.grid(row=0, column=0, padx=(14, 8), pady=14)
        self._button(add_btns, "📁  FOLDER",  self.browse_source_folder,  green=True, width=120).pack(pady=(0, 4))
        self._button(add_btns, "📦  ARCHIVE", self.browse_source_archive,             width=120).pack()
        ctk.CTkEntry(top, textvariable=self.source_var,
                      placeholder_text="Game folder, parent folder, archive (.zip/.rar/.7z), exFAT (.exfat) or ffpkg (.ffpkg)…",
                      fg_color=CARD, border_color=BORDER2, text_color=WHITE).grid(
            row=0, column=1, sticky="ew", padx=(0, 16), pady=14)

        self._button(top, "OUTPUT", self.browse_output_folder, width=100).grid(row=0, column=2, padx=(0, 8), pady=14)
        ctk.CTkEntry(top, textvariable=self.output_var, placeholder_text="Output folder...",
                      fg_color=CARD, border_color=BORDER2, text_color=WHITE).grid(row=0, column=3, sticky="ew", padx=(0, 16), pady=14)

        self._button(top, "TEMP", self.browse_temp_folder, width=90).grid(row=0, column=4, padx=(0, 8), pady=14)
        ctk.CTkEntry(top, textvariable=self.temp_var, placeholder_text="Temp folder on fast drive...",
                      fg_color=CARD, border_color=BORDER2, text_color=WHITE).grid(row=0, column=5, sticky="ew", padx=(0, 14), pady=14)

        # ── Content area (3 columns: left queue, center progress, right details)
        content = ctk.CTkFrame(main, fg_color=BLACK)
        content.grid(row=2, column=0, sticky="nsew", padx=18, pady=6)
        content.grid_columnconfigure(0, weight=2)   # left: queue + options
        content.grid_columnconfigure(1, weight=3)   # center: progress + stages
        content.grid_columnconfigure(2, weight=2)   # right: game details + cmd
        content.grid_rowconfigure(0, weight=1)

        # ── Left: Queue + Options ────────────────────────────────────────────
        left = self.panel(content, row=0, column=0, sticky="nsew", padx=(0, 10))
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(left, text="QUEUE", font=ctk.CTkFont(size=16, weight="bold"),
                      text_color=WHITE).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 4))

        # Queue listbox — tk.Listbox for native single-row selection
        lb_frame = ctk.CTkFrame(left, fg_color=CARD, corner_radius=6,
                                 border_width=1, border_color=BORDER)
        lb_frame.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 0))
        lb_frame.grid_columnconfigure(0, weight=1)

        _lb_bg   = "#111111"
        _lb_fg   = "#e8e8e8"
        _lb_sel  = "#1a5c2e"
        _lb_muted = "#888888"
        self.queue_listbox = tk.Listbox(
            lb_frame,
            bg=_lb_bg, fg=_lb_fg,
            selectbackground=_lb_sel, selectforeground="#ffffff",
            font=("Consolas", 11),
            borderwidth=0, highlightthickness=0,
            activestyle="none", relief="flat",
            height=7,
            exportselection=False,
        )
        lb_scrollbar = tk.Scrollbar(lb_frame, orient="vertical",
                                     command=self.queue_listbox.yview)
        self.queue_listbox.configure(yscrollcommand=lb_scrollbar.set)
        self.queue_listbox.grid(row=0, column=0, sticky="nsew", padx=(4, 0), pady=4)
        lb_scrollbar.grid(row=0, column=1, sticky="ns", pady=4, padx=(0, 2))
        # Clicking a row refreshes game details; arrow keys reorder
        self.queue_listbox.bind("<<ListboxSelect>>", self._on_queue_select)
        self.queue_listbox.bind("<Up>",   self._lb_key_up)
        self.queue_listbox.bind("<Down>", self._lb_key_down)

        # Queue action buttons — row 0: scan/add, row 1: reorder/remove/clear
        qbtns = ctk.CTkFrame(left, fg_color=PANEL)
        qbtns.grid(row=2, column=0, sticky="ew", padx=14, pady=(4, 10))
        qbtns.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self._button(qbtns, "SCAN / ADD", self.add_source_to_queue, green=True).grid(
            row=0, column=0, columnspan=4, sticky="ew", padx=4, pady=(4, 2))

        self._button(qbtns, "↑",         self.queue_move_up,         width=40).grid(
            row=1, column=0, sticky="ew", padx=(4, 2), pady=(2, 4))
        self._button(qbtns, "↓",         self.queue_move_down,       width=40).grid(
            row=1, column=1, sticky="ew", padx=2, pady=(2, 4))
        self._button(qbtns, "✕ REMOVE",  self.queue_remove_selected).grid(
            row=1, column=2, sticky="ew", padx=2, pady=(2, 4))
        self._button(qbtns, "🗑 CLEAR",  self.clear_queue, red=True).grid(
            row=1, column=3, sticky="ew", padx=(2, 4), pady=(2, 4))

        # ── row 3: Total / batch counter / drag-drop hint ────────────────────
        self.queue_total_var = tk.StringVar(value="Total: 0 game(s)")
        ctk.CTkLabel(left, textvariable=self.queue_total_var,
                      text_color=MUTED).grid(row=3, column=0, sticky="w", padx=14, pady=(8, 0))

        self.batch_counter_var = tk.StringVar(value="")
        self.batch_counter_label = ctk.CTkLabel(
            left, textvariable=self.batch_counter_var,
            text_color=YELLOW, font=ctk.CTkFont(size=12, weight="bold")
        )
        self.batch_counter_label.grid(row=4, column=0, sticky="w", padx=14, pady=(0, 0))

        if _HAS_DND:
            ctk.CTkLabel(left, text="↓ Drag & drop supported", text_color=MUTED,
                          font=ctk.CTkFont(size=11)).grid(row=5, column=0, sticky="w", padx=14, pady=(0, 4))

        # ── row 6: Archive password ───────────────────────────────────────────
        ctk.CTkLabel(left, text="ARCHIVE PASSWORD (OPTIONAL)",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      text_color=WHITE).grid(row=6, column=0, sticky="w", padx=14, pady=(10, 2))
        ctk.CTkLabel(left,
                      text="Only needed if your ZIP / RAR / 7z is password-protected.",
                      text_color=MUTED, font=ctk.CTkFont(size=11),
                      justify="left"
                     ).grid(row=7, column=0, sticky="w", padx=14, pady=(0, 2))
        ctk.CTkEntry(left, textvariable=self.password_var,
                      placeholder_text="Archive password (if required)",
                      show="*", fg_color=CARD, border_color=BORDER2,
                      text_color=WHITE).grid(row=8, column=0, sticky="ew", padx=14, pady=(0, 4))

        # ── row 9: Options ────────────────────────────────────────────────────
        ctk.CTkLabel(left, text="OPTIONS", font=ctk.CTkFont(size=16, weight="bold"),
                      text_color=WHITE).grid(row=9, column=0, sticky="w", padx=14, pady=(10, 6))
        opts = ctk.CTkFrame(left, fg_color=PANEL)
        opts.grid(row=10, column=0, sticky="ew", padx=14, pady=(0, 10))
        for textv, var in [
            ("Open output folder when done",       self.open_output_var),
            ("Show summary popup",                 self.summary_popup_var),
            ("Play sound on completion",           self.sound_complete_var),
            ("Play sound on errors",               self.sound_error_var),
            ("Keep intermediate PFS",              self.keep_pfs_var),
            ("Verify Output (Slower, Uses More RAM)", self.verify_output_var),
            ("Auto-clear temp after success",      self.auto_clear_temp_var),
            ("Verbose mkpfs output (debug)",       self.verbose_var),
        ]:
            ctk.CTkCheckBox(opts, text=textv, variable=var, fg_color=GREEN, hover_color=GREEN2,
                             text_color=WHITE).pack(anchor="w", pady=5)

        ctk.CTkLabel(opts,
                      text="  FOLDER button detects single games and multi-dump parent folders.",
                      text_color=MUTED, font=ctk.CTkFont(size=11),
                      justify="left").pack(anchor="w", padx=4, pady=(4, 6))

        # ── Center: Progress + Stages ────────────────────────────────────────
        center = ctk.CTkFrame(content, fg_color=BLACK)
        center.grid(row=0, column=1, sticky="nsew", padx=(0, 6))
        center.grid_columnconfigure(0, weight=1)
        center.grid_rowconfigure(0, weight=0)
        center.grid_rowconfigure(1, weight=0)

        progress = self.panel(center, row=0, column=0, sticky="ew", pady=(0, 8))
        progress.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(progress, text="OVERALL PROGRESS", text_color=WHITE,
                      font=ctk.CTkFont(size=15, weight="bold")).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 2))
        self.overall_pct_var = tk.StringVar(value="0%")
        ctk.CTkLabel(progress, textvariable=self.overall_pct_var, text_color=("#1a7a40", "#4ade80"),
                      font=ctk.CTkFont(size=24, weight="bold")).grid(row=0, column=1, sticky="e", padx=14)
        self.overall_bar = ctk.CTkProgressBar(progress, progress_color=GREEN, fg_color=("#cccccc", "#242424"), height=14)
        self.overall_bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 10))
        self.overall_bar.set(0)

        ctk.CTkLabel(progress, text="CURRENT STAGE", text_color=WHITE,
                      font=ctk.CTkFont(size=12, weight="bold")).grid(row=2, column=0, sticky="w", padx=14)
        self.stage_title_var = tk.StringVar(value="Ready")
        self.stage_detail_var = tk.StringVar(value="Add a game and start queue.")
        self.stage_pct_var = tk.StringVar(value="0%")
        ctk.CTkLabel(progress, textvariable=self.stage_title_var, text_color=WHITE,
                      font=ctk.CTkFont(size=20, weight="bold")).grid(row=3, column=0, sticky="w", padx=14, pady=(3, 0))
        ctk.CTkLabel(progress, textvariable=self.stage_pct_var, text_color=("#1a7a40", "#4ade80"),
                      font=ctk.CTkFont(size=18, weight="bold")).grid(row=3, column=1, sticky="e", padx=14)
        ctk.CTkLabel(progress, textvariable=self.stage_detail_var, text_color=MUTED,
                      wraplength=500, justify="left").grid(row=4, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 6))
        self.stage_bar = ctk.CTkProgressBar(progress, progress_color=GREEN, fg_color=("#cccccc", "#242424"), height=12)
        self.stage_bar.grid(row=5, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 10))
        self.stage_bar.set(0)

        # Stages strip — one label per stage in a horizontal row
        stages_outer = ctk.CTkFrame(progress, fg_color=PANEL, corner_radius=6)
        stages_outer.grid(row=6, column=0, columnspan=2, sticky="ew", padx=14, pady=(4, 8))
        self._stage_labels = []
        for i, (_, short) in enumerate(_STAGE_DEFS):
            if i > 0:
                ctk.CTkLabel(stages_outer, text="›", text_color=MUTED,
                              font=ctk.CTkFont(size=13)).pack(side="left", padx=0)
            lbl = ctk.CTkLabel(stages_outer, text=f"○ {short}", text_color=MUTED,
                                font=ctk.CTkFont(size=10), width=62, anchor="center")
            lbl.pack(side="left", padx=2, pady=6)
            self._stage_labels.append(lbl)

        # ShadowMount guide — sits directly below the stages strip
        sm_bar = ctk.CTkFrame(progress, fg_color=CARD, corner_radius=6, border_width=1, border_color=BORDER2)
        sm_bar.grid(row=8, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 12))
        sm_bar.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(sm_bar,
                      text="ShadowMount — How to use your .ffpfsc file",
                      text_color=WHITE, font=ctk.CTkFont(size=11, weight="bold"),
                      anchor="w"
                     ).grid(row=0, column=0, sticky="w", padx=10, pady=(7, 2))
        ctk.CTkLabel(sm_bar,
                      text=(
                          "1.   Copy the .ffpfsc file to your PS5 internal storage or an external USB drive.\n"
                          "1a.  If you already have a shortcut for this game on the XMB, delete it first — "
                          "the old entry causes a param error and the game won't appear.\n"
                          "2.   Open ShadowMount on your PS5 and let it scan. "
                          "If the game is not detected or the shortcut is not made, re-run ShadowMount.\n"
                          "3.   Select the game from the XMB and launch it — it will appear and run like a standard title."
                      ),
                      text_color=MUTED, font=ctk.CTkFont(size=11),
                      justify="left", anchor="w", wraplength=560
                     ).grid(row=1, column=0, sticky="w", padx=10, pady=(0, 8))

        # ── Compression tuning bar — horizontal, uses the empty center space ──
        tune_bar = ctk.CTkFrame(progress, fg_color=CARD, corner_radius=6,
                                 border_width=1, border_color=BORDER2)
        tune_bar.grid(row=9, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 12))
        tune_bar.grid_columnconfigure(1, weight=1)
        tune_bar.grid_columnconfigure(4, weight=1)

        ctk.CTkLabel(tune_bar, text="COMPRESSION TUNING",
                      text_color=WHITE, font=ctk.CTkFont(size=11, weight="bold"),
                      anchor="w").grid(row=0, column=0, columnspan=7, sticky="w",
                                       padx=10, pady=(7, 3))

        # ── Compression level ──
        ctk.CTkLabel(tune_bar, text="Level (0-9):", text_color=MUTED,
                      font=ctk.CTkFont(size=11), anchor="e").grid(
            row=1, column=0, sticky="e", padx=(10, 4), pady=(0, 8))
        ctk.CTkSlider(tune_bar, from_=0, to=9, number_of_steps=9,
                       variable=self.compression_level_var,
                       fg_color=BORDER2, progress_color=GREEN,
                       button_color=GREEN, button_hover_color=GREEN2,
                       height=16).grid(row=1, column=1, sticky="ew", padx=(0, 4), pady=(0, 8))
        self._comp_level_lbl = ctk.CTkLabel(tune_bar, text=str(self.compression_level_var.get()),
                                             text_color=GREEN, font=ctk.CTkFont(size=12, weight="bold"),
                                             width=22, anchor="w")
        self._comp_level_lbl.grid(row=1, column=2, padx=(0, 18), pady=(0, 8))
        def _update_comp_lbl(*_):
            self._comp_level_lbl.configure(text=str(self.compression_level_var.get()))
        self.compression_level_var.trace_add("write", _update_comp_lbl)

        # ── CPU cores ──
        ctk.CTkLabel(tune_bar, text="CPU cores (0=auto):", text_color=MUTED,
                      font=ctk.CTkFont(size=11), anchor="e").grid(
            row=1, column=3, sticky="e", padx=(0, 4), pady=(0, 8))
        ctk.CTkSlider(tune_bar, from_=0, to=16, number_of_steps=16,
                       variable=self.cpu_count_var,
                       fg_color=BORDER2, progress_color=GREEN,
                       button_color=GREEN, button_hover_color=GREEN2,
                       height=16).grid(row=1, column=4, sticky="ew", padx=(0, 4), pady=(0, 8))
        self._cpu_count_lbl = ctk.CTkLabel(tune_bar, text="auto",
                                            text_color=GREEN, font=ctk.CTkFont(size=12, weight="bold"),
                                            width=34, anchor="w")
        self._cpu_count_lbl.grid(row=1, column=5, padx=(0, 10), pady=(0, 8))
        def _update_cpu_lbl(*_):
            v = self.cpu_count_var.get()
            self._cpu_count_lbl.configure(text="auto" if v == 0 else str(v))
        self.cpu_count_var.trace_add("write", _update_cpu_lbl)

        # ── Block size ──  (new in MkPFS 0.0.7/0.0.8 — smaller = less waste for small files)
        ctk.CTkLabel(tune_bar, text="Block size:", text_color=MUTED,
                      font=ctk.CTkFont(size=11), anchor="e").grid(
            row=1, column=6, sticky="e", padx=(14, 4), pady=(0, 8))
        _block_opts = ["auto", "auto-fit", "65536", "32768", "16384"]
        _block_menu = ctk.CTkOptionMenu(
            tune_bar, values=_block_opts, variable=self.block_size_var,
            fg_color=CARD2, button_color=GREEN, button_hover_color=GREEN2,
            text_color=WHITE, dropdown_fg_color=CARD2, dropdown_text_color=WHITE,
            dropdown_hover_color=GREEN, width=96, height=24,
            font=ctk.CTkFont(size=11),
            command=lambda v: save_settings({"block_size": v}),
        )
        _block_menu.grid(row=1, column=7, sticky="w", padx=(0, 10), pady=(0, 8))

        # ── Right: Game Details + Command Preview ────────────────────────────
        right = ctk.CTkFrame(content, fg_color=BLACK)
        right.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        details = self.panel(right, row=0, column=0, sticky="ew", pady=(0, 8))
        details.grid_columnconfigure(1, weight=1)

        self.art_frame = ctk.CTkFrame(details, width=100, height=110, fg_color=BLACK,
                                       border_width=1, border_color=BORDER2)
        self.art_frame.grid(row=0, column=0, rowspan=2, padx=10, pady=10)
        self.art_frame.grid_propagate(False)
        # Plain tk.Label — CTkLabel can't cleanly switch between image=CTkImage and image=None
        self.art_label = tk.Label(self.art_frame, text="NO\nART",
                                  fg="#888888", bg="#000000",
                                  font=("Segoe UI", 9),
                                  borderwidth=0, highlightthickness=0)
        self.art_label.pack(expand=True)

        ctk.CTkLabel(details, text="GAME DETAILS", text_color=WHITE,
                      font=ctk.CTkFont(size=13, weight="bold")).grid(row=0, column=1, sticky="w", padx=4, pady=(10, 4))
        self.game_name_var = tk.StringVar(value="Name: No game selected")
        self.title_var = tk.StringVar(value="Title ID: —")
        self.source_detail_var = tk.StringVar(value="Source: —")
        self.orig_var = tk.StringVar(value="Original Size: —")
        self.files_var = tk.StringVar(value="Files: —")
        info = ctk.CTkFrame(details, fg_color=PANEL)
        info.grid(row=1, column=1, sticky="nsew", padx=(4, 10), pady=(0, 10))
        for v in [self.game_name_var, self.title_var, self.orig_var, self.files_var, self.source_detail_var]:
            ctk.CTkLabel(info, textvariable=v, text_color=WHITE, anchor="w", justify="left",
                          font=ctk.CTkFont(size=11)).pack(anchor="w", pady=2, padx=6)

        command = self.panel(right, row=1, column=0, sticky="nsew", pady=(0, 0))
        command.grid_columnconfigure(0, weight=1)
        command.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(command, text="COMMAND PREVIEW", text_color=WHITE,
                      font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, sticky="w", padx=14, pady=(10, 4))
        self.command_label = ctk.CTkLabel(command,
                                           text="Select source, output, and temp folder to preview command.",
                                           text_color=MUTED, wraplength=360, justify="left",
                                           font=ctk.CTkFont(size=11))
        self.command_label.grid(row=1, column=0, sticky="nw", padx=14, pady=(0, 10))

        # ── Bottom: Tabbed Logs / Status / History / Statistics ─────────────
        bottom = self.panel(main, row=4, column=0, sticky="nsew", padx=18, pady=(10, 14))
        bottom.grid_columnconfigure(0, weight=1)
        bottom.grid_rowconfigure(0, weight=1)

        self.bottom_tabs = ctk.CTkTabview(bottom, fg_color=BLACK, segmented_button_fg_color=PANEL,
                                           segmented_button_selected_color=GREEN,
                                           segmented_button_selected_hover_color=GREEN2,
                                           segmented_button_unselected_color=PANEL,
                                           text_color=WHITE)
        self.bottom_tabs.grid(row=0, column=0, sticky="nsew", padx=12, pady=(10, 10))

        self.bottom_tabs.add("Logs")
        self.bottom_tabs.add("Status & Stats")
        self.bottom_tabs.add("Recent Compressions")
        self.bottom_tabs.add("Statistics")
        self.bottom_tabs.add("Compatibility")

        # ── Status & Stats tab — 3 columns side by side ──────────────────────
        ss_tab = self.bottom_tabs.tab("Status & Stats")
        ss_tab.grid_columnconfigure(0, weight=2)   # STATUS
        ss_tab.grid_columnconfigure(1, weight=2)   # STATS
        ss_tab.grid_columnconfigure(2, weight=2)   # TOOLS
        ss_tab.grid_rowconfigure(0, weight=1)

        # ── STATUS (col 0) ────────────────────────────────────────────────────
        status = self.panel(ss_tab, row=0, column=0, sticky="nsew", padx=(0, 4), pady=4)
        ctk.CTkLabel(status, text="STATUS", text_color=WHITE,
                      font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=12, pady=(10, 4))
        self.big_status_var = tk.StringVar(value="Ready")
        self.big_detail_var = tk.StringVar(value="Waiting for a game.")
        ctk.CTkLabel(status, textvariable=self.big_status_var, text_color=WHITE,
                      font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", padx=12)
        ctk.CTkLabel(status, textvariable=self.big_detail_var, text_color=MUTED,
                      wraplength=320, justify="left",
                      font=ctk.CTkFont(size=11)).pack(anchor="w", padx=12, pady=(3, 10))

        # ── STATS (col 1) ─────────────────────────────────────────────────────
        stats = self.panel(ss_tab, row=0, column=1, sticky="nsew", padx=4, pady=4)
        ctk.CTkLabel(stats, text="STATS", text_color=WHITE,
                      font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=12, pady=(10, 4))
        self.speed_var       = tk.StringVar(value="Speed: —")
        self.elapsed_var     = tk.StringVar(value="Elapsed: 00:00")
        self.eta_var         = tk.StringVar(value="ETA: —")
        self.saved_var       = tk.StringVar(value="Saved: —")
        self.ratio_var       = tk.StringVar(value="Compression: —")
        self.rating_var      = tk.StringVar(value="Rating: —")
        self.temp_space_var  = tk.StringVar(value="Temp Needed: —")
        for v in [self.speed_var, self.elapsed_var, self.eta_var,
                  self.saved_var, self.ratio_var, self.rating_var, self.temp_space_var]:
            ctk.CTkLabel(stats, textvariable=v, text_color=WHITE, anchor="w",
                          font=ctk.CTkFont(size=11)).pack(anchor="w", padx=12, pady=2)
        # bottom padding
        ctk.CTkLabel(stats, text="", height=6).pack()

        # ── TOOLS (col 2) ─────────────────────────────────────────────────────
        tools_frame = self.panel(ss_tab, row=0, column=2, sticky="nsew", padx=(4, 0), pady=4)
        ctk.CTkLabel(tools_frame, text="TOOLS", text_color=WHITE,
                      font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=12, pady=(10, 6))
        self._button(tools_frame, "OPEN OUTPUT FOLDER",    self.open_output_folder,  height=34).pack(fill="x", padx=12, pady=3)
        self._button(tools_frame, "EXPORT RAW LOG",        self.open_raw_log,        height=34).pack(fill="x", padx=12, pady=3)
        self._button(tools_frame, "🗑  Clear Temp Files",  self.clear_temp_files,    height=34).pack(fill="x", padx=12, pady=3)
        self._button(tools_frame, "📦  Export Diagnostic", self.export_diagnostics,  height=34).pack(fill="x", padx=12, pady=3)
        self._button(tools_frame, "📋  Copy Last Result",  self.copy_last_result,    height=34).pack(fill="x", padx=12, pady=(3, 10))

        # Logs tab
        log_tab = self.bottom_tabs.tab("Logs")
        log_tab.grid_columnconfigure(0, weight=1)
        log_tab.grid_rowconfigure(0, weight=1)
        log_head = ctk.CTkFrame(log_tab, fg_color=BLACK)
        log_head.grid(row=0, column=0, sticky="ew")
        log_head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(log_head, text="LOGS", text_color=WHITE,
                      font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, sticky="w")
        self._button(log_head, "CLEAR LOGS", self.clear_logs, width=110).grid(row=0, column=1, padx=4)
        self.log_box = ctk.CTkTextbox(log_tab, fg_color=BLACK, border_width=1, border_color=BORDER,
                                       text_color="#94a3b8", font=ctk.CTkFont(family="Consolas", size=12), wrap="none")
        self.log_box.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        log_tab.grid_rowconfigure(1, weight=1)
        # Per-level colour tags on the underlying tk.Text widget
        try:
            t = self.log_box._textbox
            t.tag_configure("SUCCESS",  foreground="#4ade80")
            t.tag_configure("OK",       foreground="#4ade80")
            t.tag_configure("ERROR",    foreground="#f87171")
            t.tag_configure("WARN",     foreground="#facc15")
            t.tag_configure("INFO",     foreground="#94a3b8")
            t.tag_configure("PROGRESS", foreground="#60a5fa")
            t.tag_configure("DEBUG",    foreground="#555555")
        except Exception:
            pass

        # History tab
        hist_tab = self.bottom_tabs.tab("Recent Compressions")
        hist_tab.grid_columnconfigure(0, weight=1)
        hist_tab.grid_rowconfigure(1, weight=1)
        hist_head = ctk.CTkFrame(hist_tab, fg_color=BLACK)
        hist_head.grid(row=0, column=0, sticky="ew")
        hist_head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hist_head, text="RECENT COMPRESSIONS", text_color=WHITE,
                      font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, sticky="w")
        self._button(hist_head, "REFRESH", self.refresh_history, width=110).grid(row=0, column=1, padx=4)
        self.history_box = ctk.CTkTextbox(hist_tab, fg_color=BLACK, border_width=1, border_color=BORDER,
                                           text_color=WHITE, font=ctk.CTkFont(family="Consolas", size=12), wrap="none")
        self.history_box.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.refresh_history()

        # Statistics tab
        stats_tab = self.bottom_tabs.tab("Statistics")
        stats_tab.grid_columnconfigure(0, weight=1)
        stats_tab.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(stats_tab, text="COMPRESSION STATISTICS", text_color=WHITE,
                      font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.stats_box = ctk.CTkTextbox(stats_tab, fg_color=BLACK, border_width=1, border_color=BORDER,
                                         text_color=WHITE, font=ctk.CTkFont(family="Consolas", size=13), wrap="none")
        self.stats_box.grid(row=1, column=0, sticky="nsew")
        self._button(stats_tab, "REFRESH STATS", self.refresh_statistics, width=140).grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.refresh_statistics()

        # ── Compatibility tab ─────────────────────────────────────────────────
        compat_tab = self.bottom_tabs.tab("Compatibility")
        compat_tab.grid_columnconfigure(0, weight=1)
        compat_tab.grid_columnconfigure(1, weight=2)
        compat_tab.grid_rowconfigure(0, weight=1)

        # ── Left: submit form ─────────────────────────────────────────────────
        form_outer = ctk.CTkScrollableFrame(compat_tab, fg_color=PANEL, border_width=1,
                                             border_color=BORDER, corner_radius=10)
        form_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=4)
        form_outer.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form_outer, text="SUBMIT COMPATIBILITY REPORT",
                      text_color=WHITE, font=ctk.CTkFont(size=13, weight="bold")
                     ).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 8))

        # Form fields
        self._compat_title_var      = tk.StringVar()
        self._compat_titleid_var    = tk.StringVar()
        self._compat_origsize_var   = tk.StringVar()
        self._compat_compsize_var   = tk.StringVar()
        self._compat_smver_var      = tk.StringVar()
        self._compat_storage_var    = tk.StringVar(value="Internal PS5 SSD")
        self._compat_status_var     = tk.StringVar(value="Working")

        field_rows = [
            ("Game Title",       self._compat_title_var,   False),
            ("Title ID",         self._compat_titleid_var, False),
            ("Original Size",    self._compat_origsize_var,False),
            ("Compressed Size",  self._compat_compsize_var,False),
            ("ShadowMount Ver.", self._compat_smver_var,   False),
        ]
        for ri, (lbl, var, _) in enumerate(field_rows, start=1):
            ctk.CTkLabel(form_outer, text=lbl + ":", text_color=MUTED,
                          font=ctk.CTkFont(size=11)).grid(row=ri, column=0, sticky="w", padx=12, pady=2)
            ctk.CTkEntry(form_outer, textvariable=var, fg_color=CARD,
                          border_color=BORDER2, text_color=WHITE,
                          font=ctk.CTkFont(size=11)).grid(row=ri, column=1, sticky="ew", padx=(4, 12), pady=2)

        ctk.CTkLabel(form_outer, text="Storage:", text_color=MUTED,
                      font=ctk.CTkFont(size=11)).grid(row=6, column=0, sticky="w", padx=12, pady=2)
        ctk.CTkOptionMenu(form_outer, variable=self._compat_storage_var,
                           values=["Internal PS5 SSD", "USB SSD", "USB HDD", "External HDD"],
                           fg_color=CARD2, button_color=CARD2, button_hover_color=BORDER2,
                           text_color=WHITE, font=ctk.CTkFont(size=11)
                          ).grid(row=6, column=1, sticky="ew", padx=(4, 12), pady=2)

        ctk.CTkLabel(form_outer, text="Status:", text_color=MUTED,
                      font=ctk.CTkFont(size=11)).grid(row=7, column=0, sticky="w", padx=12, pady=2)
        status_row = ctk.CTkFrame(form_outer, fg_color="transparent")
        status_row.grid(row=7, column=1, sticky="w", padx=(4, 12), pady=2)
        for st, col in [("✅ Working", GREEN), ("⚠ Partial", YELLOW), ("❌ Not Working", RED)]:
            ctk.CTkRadioButton(status_row, text=st, variable=self._compat_status_var,
                                value=st.split(" ", 1)[1],
                                fg_color=col, hover_color=col,
                                text_color=WHITE, font=ctk.CTkFont(size=11)
                               ).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(form_outer, text="Performance Notes:", text_color=MUTED,
                      font=ctk.CTkFont(size=11)).grid(row=8, column=0, sticky="nw", padx=12, pady=(6, 2))
        self._compat_notes_box = ctk.CTkTextbox(form_outer, fg_color=CARD, border_width=1,
                                                 border_color=BORDER2, text_color=WHITE,
                                                 font=ctk.CTkFont(size=11), height=60, wrap="word")
        self._compat_notes_box.grid(row=8, column=1, sticky="ew", padx=(4, 12), pady=(6, 4))

        # ── Share to community checkbox ───────────────────────────────────────
        self._compat_share_var = tk.BooleanVar(value=True)
        share_row = ctk.CTkFrame(form_outer, fg_color="transparent")
        share_row.grid(row=9, column=0, columnspan=2, sticky="ew", padx=12, pady=(4, 0))
        ctk.CTkCheckBox(share_row, text="Share anonymously to community database",
                        variable=self._compat_share_var,
                        text_color=MUTED, font=ctk.CTkFont(size=11),
                        fg_color=GREEN, hover_color=GREEN2,
                        border_color=BORDER2).pack(side="left")
        self._compat_share_status = ctk.CTkLabel(share_row, text="", text_color=MUTED,
                                                  font=ctk.CTkFont(size=10))
        self._compat_share_status.pack(side="left", padx=(8, 0))

        btn_row = ctk.CTkFrame(form_outer, fg_color="transparent")
        btn_row.grid(row=10, column=0, columnspan=2, sticky="ew", padx=12, pady=(4, 12))
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)
        self._button(btn_row, "✚  Submit Report", self.submit_compat_report,
                      green=True).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self._button(btn_row, "⟳  Auto-fill from last game", self._compat_autofill
                     ).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        # ── Right: compatibility list ─────────────────────────────────────────
        list_frame = ctk.CTkFrame(compat_tab, fg_color=PANEL, border_width=1,
                                   border_color=BORDER, corner_radius=10)
        list_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=4)
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(1, weight=1)

        list_head = ctk.CTkFrame(list_frame, fg_color="transparent")
        list_head.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        list_head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(list_head, text="COMPATIBILITY LIST", text_color=WHITE,
                      font=ctk.CTkFont(size=13, weight="bold")).grid(row=0, column=0, sticky="w")
        hbtn = ctk.CTkFrame(list_head, fg_color="transparent")
        hbtn.grid(row=0, column=1)
        self._button(hbtn, "⟳ Refresh", self.refresh_compat_list, width=80).pack(side="left", padx=(0, 4))
        self._button(hbtn, "CSV Export", self.export_compat_csv,   width=90).pack(side="left")

        self.compat_box = ctk.CTkTextbox(list_frame, fg_color=BLACK, border_width=1, border_color=BORDER,
                                          text_color=WHITE, font=ctk.CTkFont(family="Consolas", size=11),
                                          wrap="word", state="disabled")
        self.compat_box.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.refresh_compat_list()

        # Footer
        footer = ctk.CTkFrame(main, fg_color=BLACK)
        footer.grid(row=5, column=0, sticky="ew", padx=18, pady=(0, 8))
        self.footer_var = tk.StringVar(value="● Ready")
        ctk.CTkLabel(footer, textvariable=self.footer_var, text_color=("#1a7a40", "#4ade80")).pack(side="left")
        ctk.CTkLabel(footer, text=f"{APP_VERSION}  |  Bizkut Backend  |  {MKPFS_NAME} v{MKPFS_VERSION}", text_color=MUTED).pack(side="right")

        self.update_queue_box()

        # ── Drag & drop registration ─────────────────────────────────────────
        if _HAS_DND:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._on_drop)

    # ── Theme toggle ─────────────────────────────────────────────────────────
    def _toggle_theme(self):
        self._theme = "light" if self._theme == "dark" else "dark"
        ctk.set_appearance_mode(self._theme)
        # No manual recoloring needed — all color constants are (light, dark) tuples
        # so CTk picks the correct value automatically on appearance mode change.

    def open_settings(self):
        if self._settings_win and self._settings_win.winfo_exists():
            self._settings_win.focus()
            return
        self._settings_win = SettingsWindow(self.root, self)

    # ── Drag & drop ───────────────────────────────────────────────────────────
    def _on_drop(self, event):
        try:
            paths = self.root.tk.splitlist(event.data)
        except Exception:
            paths = [event.data]
        for raw in paths:
            p = Path(raw.strip("{}").strip())
            if p.exists():
                self.source_var.set(str(p))
                self.add_source_to_queue()   # handles folders AND archives uniformly
            else:
                self.log("WARN", f"Dropped path not found: {p}")

    # ── Folder browse ─────────────────────────────────────────────────────────
    def browse_source_folder(self):
        """Folder picker — single game folder or parent folder containing multiple dumps."""
        path = filedialog.askdirectory(title="Select PS5 game folder or parent folder")
        if not path:
            return
        p = Path(path)
        self.source_var.set(str(p))
        if not self.output_var.get():
            self.output_var.set(str(p.parent))
        if not self.temp_var.get():
            self.temp_var.set(str(p.parent / "_ffpfsc_temp"))
        self.preview_light(p)
        self.add_source_to_queue()

    def browse_source_archive(self):
        """File picker — select a .zip / .rar / .7z archive, .exfat, or .ffpkg disk image."""
        path = filedialog.askopenfilename(
            title="Select archive or disk image",
            filetypes=[
                ("Supported files", "*.zip *.rar *.7z *.exfat *.ffpkg"),
                ("Disk images",     "*.exfat *.ffpkg"),
                ("Archives",        "*.zip *.rar *.7z"),
                ("ZIP",             "*.zip"),
                ("RAR",             "*.rar"),
                ("7-Zip",           "*.7z"),
                ("All files",       "*.*"),
            ]
        )
        if not path:
            return
        p = Path(path)
        self.source_var.set(str(p))
        if not self.output_var.get():
            self.output_var.set(str(p.parent))
        if not self.temp_var.get():
            self.temp_var.set(str(p.parent / "_ffpfsc_temp"))
        self.add_source_to_queue()

    def browse_output_folder(self):
        p = filedialog.askdirectory(title="Select output folder")
        if p:
            self.output_var.set(p)
            if not self.temp_var.get():
                self.temp_var.set(str(Path(p) / "_ffpfsc_temp"))
            save_settings({"output_folder": p})
            self.update_command_preview()

    def browse_temp_folder(self):
        p = filedialog.askdirectory(title="Select temp folder")
        if p:
            tp = str(Path(p) / "_ffpfsc_temp")
            self.temp_var.set(tp)
            save_settings({"temp_folder": tp})
            self.update_command_preview()

    def preview_light(self, p: Path):
        self.game_name_var.set(f"Name: {guess_game_name(p)}")
        self.title_var.set(f"Title ID: {parse_title_id(p)}")
        self.source_detail_var.set(f"Source: {p}")
        self.orig_var.set("Original Size: click Scan / Add")
        self.files_var.set("Files: click Scan / Add")
        self.load_art(find_artwork(p))
        self.update_command_preview()

    def load_art(self, art):
        # Cache: skip disk I/O if the path hasn't changed
        art_key = str(art) if art else None
        if art_key == getattr(self, "_loaded_art_key", object()):
            return
        self._loaded_art_key = art_key

        if Image and ImageTk and art and art.exists():
            try:
                img = Image.open(art).convert("RGBA")
                img.thumbnail((130, 130))
                tk_img = ImageTk.PhotoImage(img)
                self.art_img = tk_img          # hold reference — GC would delete the Tcl image
                self.art_label.configure(image=tk_img, text="", bg="#000000")
                return
            except Exception as _art_err:
                pass   # fall through to placeholder
        # No art or load failed
        self.art_img = None
        self.art_label.configure(image="", text="NO\nART", fg="#888888", bg="#000000")

    # ── Queue management ──────────────────────────────────────────────────────
    @staticmethod
    def _clean_path_str(raw: str) -> str:
        """Strip whitespace and surrounding quotes Windows sometimes adds."""
        s = raw.strip()
        if len(s) >= 2 and s[0] in ('"', "'") and s[-1] == s[0]:
            s = s[1:-1].strip()
        return s

    def add_source_to_queue(self):
        src_str = self._clean_path_str(self.source_var.get())
        if not src_str:
            messagebox.showerror("Nothing selected",
                                  "Enter or browse to a game folder, parent folder, archive (.zip/.rar/.7z), exFAT (.exfat) or ffpkg (.ffpkg).")
            return
        src = Path(src_str)
        if not src.exists():
            messagebox.showerror("Path not found",
                                  f"This path does not exist:\n{src}")
            return

        # ── Direct .exfat / .ffpkg disk image — no extraction, passed straight to backend ─
        if src.is_file() and src.suffix.lower() in (".exfat", ".ffpkg"):
            item = GameItem.from_exfat(src)
            self.queue.append(item)
            self.update_queue_box(select_item=item)
            label = "exFAT image" if src.suffix.lower() == ".exfat" else "ffpkg image"
            self.log("OK", f"{label} queued: {src.name}  [{format_size(item.size)}]")
            self.status_update("Ready",
                                f"{label} queued: {src.name}",
                                "Ready", 0, 0, "00:00", "—", "—")
            return

        # ── Single archive file — queue as placeholder, extract on its turn ─────
        if src.is_file() and src.suffix.lower() in (".zip", ".rar", ".7z"):
            item = GameItem.from_archive(src)
            self.queue.append(item)
            self.update_queue_box(select_item=item)
            self.log("OK", f"Archive queued: {src.name}  [{format_size(item.size)}]")
            self.status_update("Ready",
                                f"Archive queued — will extract when compression starts: {src.name}",
                                "Ready", 0, 0, "00:00", "—", "—")
            return

        # ── Direct PS5 game folder ────────────────────────────────────────────
        if is_game_folder(src):
            warns = validate_game_structure(src)
            if warns:
                msg = "\n".join(f"• {w}" for w in warns)
                if not messagebox.askyesno(
                    "Game Structure Warning",
                    f"Potential issues detected:\n\n{msg}\n\n"
                    "Expected: sce_sys/param.json and eboot.bin\n\nAdd anyway?"
                ):
                    return
            self.status_update("Scanning", f"Reading {src.name}…",
                                "Scanning Files", 0, 0, "00:00", "—", "—")
            def _scan_single(p=src):
                try:
                    self.scan_q.put(("ok", GameItem(p)))
                except Exception as e:
                    self.scan_q.put(("error", str(e)))
            threading.Thread(target=_scan_single, daemon=True).start()
            return

        # ── Parent / unknown folder ───────────────────────────────────────────
        # Scan for extracted game folders AND loose archive files
        self.status_update("Scanning", f"Scanning {src.name}…",
                            "Scanning Files", 0, 0, "00:00", "—", "—")
        self.log("INFO", f"Scanning folder: {src}")

        def _scan_folder(p=src):
            try:
                # 1. Look for extracted game folders first
                self.log("INFO", "Looking for PS5 game folders…")
                games = find_game_folders(p)
                if games:
                    self.log("INFO", f"Found {len(games)} game folder(s)")
                    if len(games) == 1:
                        try:
                            self.scan_q.put(("ok", GameItem(games[0])))
                        except Exception as e:
                            self.scan_q.put(("error", str(e)))
                    else:
                        self.scan_q.put(("multi_found", games))
                    return

                # 2. No extracted games — look for .exfat/.ffpkg images and archive files (one level deep)
                self.log("INFO", "No game folders found — scanning for disk images and archives…")
                image_files = []   # .exfat and .ffpkg
                archives    = []
                try:
                    for f in p.iterdir():
                        if not f.is_file():
                            continue
                        suffix = f.suffix.lower()
                        if suffix in (".exfat", ".ffpkg"):
                            image_files.append(f)
                            label = "exFAT" if suffix == ".exfat" else "ffpkg"
                            self.log("INFO", f"  Found {label} image: {f.name}")
                        elif suffix in (".zip", ".rar", ".7z"):
                            archives.append(f)
                            self.log("INFO", f"  Found archive: {f.name}")
                except Exception as e:
                    self.log("WARN", f"Could not list folder contents: {e}")

                image_files.sort(key=lambda f: f.name.lower())
                archives.sort(key=lambda f: f.name.lower())

                if image_files:
                    self.log("INFO", f"Found {len(image_files)} disk image(s) — queuing directly (no extraction needed)")
                    if len(image_files) == 1:
                        self.scan_q.put(("ok", GameItem.from_exfat(image_files[0])))
                    else:
                        self.scan_q.put(("exfat_found", image_files))
                    return

                if archives:
                    self.log("INFO", f"Found {len(archives)} archive(s) — queuing for extraction")
                    self.scan_q.put(("archives_found", archives))
                    return

                # 3. Nothing useful found
                self.log("WARN", f"No games, disk images, or archives found in {p}")
                self.scan_q.put((
                    "error",
                    f"Nothing found in:\n{p}\n\n"
                    "Expected either:\n"
                    "  • Game folders containing sce_sys/ and eboot.bin\n"
                    "  • Disk images (.exfat or .ffpkg)\n"
                    "  • Archive files (.zip / .rar / .7z)"
                ))
            except Exception as e:
                self.log("ERROR", f"Folder scan crashed: {e}")
                self.scan_q.put(("error", f"Scan error: {e}"))

        threading.Thread(target=_scan_folder, daemon=True).start()

    def _extract_and_queue_archive(self, archive: Path):
        """Extract *archive* to the temp folder (background thread) with live progress, then queue."""
        temp_base = self.temp_var.get().strip()
        if not temp_base:
            temp_base = str(archive.parent / "_ffpfsc_temp")
            self.temp_var.set(temp_base)
        extract_root = Path(temp_base) / "_extracted"

        self.log("INFO", f"Extracting archive: {archive.name}")
        self.status_update("Extracting", f"Unpacking {archive.name}…  0%",
                            "Scanning Files", 0, 0, "00:00", "—", "—")
        # Show Logs tab so the user can watch per-file lines
        try:
            self.bottom_tabs.set("Logs")
        except Exception:
            pass

        # Throttle: only update status every 2 % to avoid flooding the queue
        _last_pct = [-1]
        def _progress(pct: int, filename: str):
            if pct - _last_pct[0] >= 2 or pct >= 100:
                _last_pct[0] = pct
                short = Path(filename).name[:50]
                self.status_update(
                    "Extracting",
                    f"Unpacking {archive.name}…  {pct}%\n{short}",
                    "Scanning Files", pct, pct, "—", "—", "—"
                )

        archive_password = self.password_var.get().strip()

        def worker():
            try:
                extracted_root = ArchiveExtractor.extract(
                    archive, extract_root,
                    log_fn=self.log, progress_fn=_progress,
                    password=archive_password
                )
                self.status_update("Scanning", "Extraction done — scanning for games…",
                                    "Scanning Files", 98, 98, "—", "—", "—")
                games = find_game_folders(extracted_root)
                if not games:
                    # No recognised sub-games — try the root itself
                    try:
                        self.scan_q.put(("ok", GameItem(extracted_root)))
                    except Exception as e:
                        self.scan_q.put(("error", f"No PS5 game found in archive: {e}"))
                elif len(games) == 1:
                    try:
                        self.scan_q.put(("ok", GameItem(games[0])))
                    except Exception as e:
                        self.scan_q.put(("error", str(e)))
                else:
                    self.scan_q.put(("multi_found", games))
            except Exception as exc:
                self.log("ERROR", f"Extraction failed: {exc}")
                self.scan_q.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    # ── Extract archive when it reaches the front of the queue ───────────────
    def _extract_queued_item(self, item):
        """Extract item.archive_path in a background thread, then call start() again."""
        archive = item.archive_path
        temp_base = self.temp_var.get().strip()
        if not temp_base:
            temp_base = str(archive.parent / "_ffpfsc_temp")
            self.temp_var.set(temp_base)
        extract_root = Path(temp_base) / "_extracted"

        item.status = "Extracting"
        self.update_queue_box()
        self.start_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")

        self.log("INFO", f"Extracting archive: {archive.name}")
        self.status_update("Extracting", f"Unpacking {archive.name}…  0%",
                            "Scanning Files", 0, 0, "00:00", "—", "—")
        try:
            self.bottom_tabs.set("Logs")
        except Exception:
            pass

        _last_pct = [-1]
        def _progress(pct, filename):
            if pct - _last_pct[0] >= 2 or pct >= 100:
                _last_pct[0] = pct
                self.status_update("Extracting",
                                    f"Unpacking {archive.name}…  {pct}%",
                                    "Scanning Files", pct, pct, "—", "—", "—")

        pwd = self.password_var.get().strip()

        def worker():
            try:
                extracted_root = ArchiveExtractor.extract(
                    archive, extract_root,
                    log_fn=self.log, progress_fn=_progress, password=pwd
                )
                games = find_game_folders(extracted_root)
                game_path = games[0] if games else extracted_root

                # Update item in-place with real game info
                item.path         = game_path
                item.archive_path = None
                item.name         = guess_game_name(game_path)
                item.title_id     = parse_title_id(game_path)
                item.size         = folder_size(game_path)
                item.files        = file_count(game_path)
                item.artwork      = find_artwork(game_path)
                item.status       = "Queued"
                self._extract_q.put(("ok", item))
            except Exception as exc:
                self.log("ERROR", f"Extraction failed: {exc}")
                self._extract_q.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    # ── Listbox keyboard reorder ──────────────────────────────────────────────
    def _lb_key_up(self, _event=None):
        self.queue_move_up()
        return "break"   # prevent default selection-navigation

    def _lb_key_down(self, _event=None):
        self.queue_move_down()
        return "break"

    # ── Queue selection helper ─────────────────────────────────────────────────
    def _queue_sel_idx(self) -> int | None:
        """Return the currently selected listbox index, or None."""
        sel = self.queue_listbox.curselection()
        return int(sel[0]) if sel else None

    def _on_queue_select(self, _event=None):
        """When a row is clicked, update the game details panel."""
        idx = self._queue_sel_idx()
        if idx is not None and idx < len(self.queue):
            self.update_game_details(self.queue[idx])

    # ── Queue management ──────────────────────────────────────────────────────
    def queue_move_up(self):
        idx = self._queue_sel_idx()
        if idx is None or idx == 0:
            return
        if self._batch_running and idx == 1:
            return  # can't move above the active game
        moved = self.queue[idx]                                   # capture before swap
        self.queue[idx], self.queue[idx - 1] = self.queue[idx - 1], self.queue[idx]
        self.update_queue_box(select_item=moved)                  # finds moved item at idx-1

    def queue_move_down(self):
        idx = self._queue_sel_idx()
        if idx is None or idx >= len(self.queue) - 1:
            return
        if self._batch_running and idx == 0:
            return  # can't move the active game
        moved = self.queue[idx]                                   # capture before swap
        self.queue[idx], self.queue[idx + 1] = self.queue[idx + 1], self.queue[idx]
        self.update_queue_box(select_item=moved)                  # finds moved item at idx+1

    def queue_remove_selected(self):
        idx = self._queue_sel_idx()
        if idx is None:
            return
        # Don't allow removing the currently running game
        if self._batch_running and idx == 0:
            messagebox.showwarning("In Progress",
                                   "The first game in the queue is currently compressing.\n"
                                   "Cancel the compression first to remove it.")
            return
        # Decide which item to show after removal (next item, or previous if at end)
        if len(self.queue) > 1:
            next_item = self.queue[idx + 1] if idx + 1 < len(self.queue) else self.queue[idx - 1]
        else:
            next_item = None
        self.queue.pop(idx)
        self.update_queue_box(select_item=next_item)

    def remove_first(self):
        """Legacy helper — removes the first (non-running) queue entry."""
        if self.queue and not self._batch_running:
            self.queue.pop(0)
        self.update_queue_box()

    def clear_queue(self):
        if self._batch_running:
            ok = messagebox.askyesno("Clear Queue",
                                      "A compression is running. Clear the waiting games?\n"
                                      "(The current game will finish normally.)")
            if not ok:
                return
            self.queue[1:] = []   # keep index-0 (running game), clear the rest
        else:
            self.queue.clear()
        self.update_queue_box()

    def update_queue_box(self, select_item=None):
        """Rebuild the listbox.

        select_item: if given, that GameItem will be highlighted after the
        rebuild (used by move-up/down so the correct item is tracked even
        though the listbox selection is stale).  When omitted the previously
        selected item is looked up by object identity; falls back to row 0.
        """
        # Decide which item to keep selected
        if select_item is None:
            prev_idx  = self._queue_sel_idx()
            select_item = (self.queue[prev_idx]
                           if prev_idx is not None and prev_idx < len(self.queue)
                           else None)

        self.queue_listbox.delete(0, "end")
        if not self.queue:
            self.queue_listbox.insert("end", "  Queue is empty")
            self.queue_listbox.itemconfig(0, fg="#555555")
            self.queue_total_var.set("Total: 0 game(s)")
            self._details_item = None
            return

        total = sum(x.size for x in self.queue)
        for i, item in enumerate(self.queue):
            prefix = "▶ " if (self._batch_running and i == 0) else f"{i + 1}. "
            line = f"{prefix}{item.title_id}  {item.name}  [{format_size(item.size)}]  {item.status}"
            self.queue_listbox.insert("end", line)
            if self._batch_running and i == 0:
                self.queue_listbox.itemconfig(i, fg="#4ade80")
            elif item.status == "Failed":
                self.queue_listbox.itemconfig(i, fg="#f87171")
            elif item.status == "Done":
                self.queue_listbox.itemconfig(i, fg="#888888")

        self.queue_total_var.set(f"Total: {len(self.queue)} game(s)  |  {format_size(total)}")

        # Find the target item's new index; fall back to row 0
        try:
            sel = self.queue.index(select_item) if select_item in self.queue else 0
        except (ValueError, TypeError):
            sel = 0
        self.queue_listbox.selection_set(sel)
        self.queue_listbox.see(sel)

        # Only refresh the details panel when the selected item actually changed.
        # Using `is` (reference equality) is safe here: we hold _details_item as a
        # real reference so Python cannot reuse the address while it lives in the queue.
        sel_item = self.queue[sel]
        if sel_item is not self._details_item:
            self.update_game_details(sel_item)

    def update_game_details(self, item):
        self._details_item = item   # record before any call that might raise
        self.game_name_var.set(f"Name: {item.name}")
        self.title_var.set(f"Title ID: {item.title_id}")
        self.source_detail_var.set(f"Source: {item.path}")
        self.orig_var.set(f"Original Size: {format_size(item.size)}")
        self.files_var.set(f"Files: {item.files:,}")
        self.load_art(item.artwork)
        self._refresh_space_for_item(item)
        self.update_command_preview()

    def _refresh_space_for_item(self, item=None):
        """Recalculate free-space vs what this game needs and update the stats label."""
        if item is None:
            item = self.queue[0] if self.queue else None
        if item is None or getattr(item, "size", 0) == 0:
            self.temp_space_var.set("Temp Needed: —")
            return
        try:
            tp = self.temp_var.get().strip()
            op = self.output_var.get().strip()
            temp_dir = Path(tp) if tp else None
            out_dir  = Path(op) if op else None
            if temp_dir is None:
                self.temp_space_var.set(f"Peak Needed: ~{format_size(item.size * 2.2)}")
                return
            same  = same_drive(temp_dir, out_dir) if out_dir else True
            peak  = estimate_peak_space_needed(item.size, same)
            free  = get_free_space(temp_dir)
            out_free = get_free_space(out_dir) if out_dir else 0
            ok    = free >= peak
            flag  = "✓ OK" if ok else "⚠ LOW"
            self.temp_space_var.set(
                f"Need: ~{format_size(peak)}  |  Temp Free: {format_size(free)}  "
                f"|  Out Free: {format_size(out_free)}  |  {flag}"
            )
        except Exception:
            self.temp_space_var.set(f"Peak Needed: ~{format_size(item.size * 2.2)}")

    def update_command_preview(self):
        item = self.queue[0] if self.queue else None
        # Archive placeholders have no path yet — show a friendly message instead
        if item and getattr(item, "archive_path", None):
            self.command_label.configure(
                text=f"📦 {item.name} — archive will be extracted before compression starts.")
            return
        src = self.source_var.get().strip()
        if not item and src and Path(src).exists():
            p = Path(src)
            pycmd = get_backend_python_command() or ["python"]
            cmd = pycmd + ["-u", str(backend_base_dir() / "cli.py"), str(p),
                           self.output_var.get().strip() or str(p.parent), "--overwrite"]
        elif item:
            try:
                cmd, _, _, _ = self.build_command(item)
            except Exception:
                self.command_label.configure(text="Select output and temp folder to preview command.")
                return
        else:
            self.command_label.configure(text="Select source, output, and temp folder to preview command.")
            return
        self.command_label.configure(text=" ".join(f'"{x}"' if " " in x else x for x in cmd))

    def build_command(self, item):
        out = Path(self.output_var.get().strip())
        temp = Path(self.temp_var.get().strip())
        backend = backend_base_dir()
        cli_py = Path("backend") / "cli.py"  # macOS-ready pathlib form
        cli_py = backend / "cli.py"
        pycmd = get_backend_python_command()
        if not pycmd:
            raise RuntimeError("Python was not found. Install Python or run RUN.bat instead of the EXE.")
        cmd = pycmd + ["-u", str(cli_py), str(item.path), str(out)]
        if self.batch_var.get():
            cmd.append("--batch")
        if self.keep_pfs_var.get():
            cmd.append("--keep-pfs")
        if self.verify_output_var.get():
            cmd.append("--verify")
        # MkPFS 0.0.8 tuning
        comp_level = self.compression_level_var.get()
        if comp_level != 7:  # only pass if non-default
            cmd += ["--compression-level", str(comp_level)]
        cpu = self.cpu_count_var.get()
        if cpu != 0:
            cmd += ["--cpu-count", str(cpu)]
        block_size = self.block_size_var.get()
        if block_size and block_size != "auto":
            cmd += ["--block-size", block_size]
        if self.verbose_var.get():
            cmd.append("--verbose")
        # Pass user temp dir so mkpfs uses the fast drive too
        temp_str = self.temp_var.get().strip()
        if temp_str:
            cmd += ["--temp-dir", temp_str]
        cmd.append("--overwrite")
        return cmd, backend, out if out.suffix.lower() != ".ffpfsc" else out.parent, temp

    # ── Feature 5: Auto-clear temp ────────────────────────────────────────────
    def _auto_clear_temp(self):
        """Silently clear temp folder contents after a successful compression."""
        tp = self.temp_var.get().strip()
        if not tp:
            return
        temp_dir = Path(tp)
        if not temp_dir.exists():
            return
        freed = 0
        errors = 0
        for p in list(temp_dir.iterdir()):
            try:
                sz = get_folder_size(p) if p.is_dir() else (p.stat().st_size if p.is_file() else 0)
                if p.is_dir():
                    shutil.rmtree(str(p), ignore_errors=True)
                else:
                    p.unlink(missing_ok=True)
                freed += sz
            except Exception:
                errors += 1
        msg = f"🗑  Auto-cleared temp: freed {format_size(freed)}"
        if errors:
            msg += f" ({errors} item(s) could not be removed)"
        self.log("OK", msg)

    # ── Feature 4: Batch auto-advance ─────────────────────────────────────────
    def _update_batch_counter(self):
        if not self._batch_running:
            self.batch_counter_var.set("")
            return
        current = self._batch_done + self._batch_failed + 1
        self.batch_counter_var.set(
            f"Game {current}/{self._batch_total}  |  ✓ {self._batch_done}  ✗ {self._batch_failed}"
        )

    def _batch_auto_start(self):
        """Start the next game in the queue — rechecks disk space before each game."""
        if not self.queue:
            self._batch_running = False
            self.start_btn.configure(state="normal")
            self.cancel_btn.configure(state="disabled")
            self._update_batch_counter()
            return
        item = self.queue[0]
        self.update_game_details(item)   # refreshes art + space stats for next game

        # ── Space pre-flight dialog (auto-dismisses if OK, waits if LOW) ─────────
        try:
            tp = self.temp_var.get().strip()
            op = self.output_var.get().strip()
            if tp and op:
                td = Path(tp); od = Path(op)
                peak = estimate_peak_space_needed(item.size, same_drive(td, od))
                free = get_free_space(td)
                self.log("INFO",
                    f"Space check — {item.name}: "
                    f"Need {format_size(peak)} | Temp free {format_size(free)} "
                    f"| {'✓ OK' if free >= peak else '⚠ LOW'}"
                )
                diag = SpaceDiagnosticsDialog(self.root, item, td, od)
                self.root.wait_window(diag)
                if not diag.proceed:
                    self._batch_running = False
                    self.start_btn.configure(state="normal")
                    self.cancel_btn.configure(state="disabled")
                    self._update_batch_counter()
                    return
        except Exception as e:
            self.log("WARN", f"Space pre-check skipped: {e}")

        # Archive placeholder — extract first
        if getattr(item, "archive_path", None):
            self._extract_queued_item(item)
            return
        try:
            cmd, cwd, out_dir, temp_dir = self.build_command(item)
        except Exception as e:
            self.log("ERROR", f"Auto-advance build_command failed: {e}")
            self._batch_running = False
            self.start_btn.configure(state="normal")
            self.cancel_btn.configure(state="disabled")
            self._update_batch_counter()
            return
        item.status = "Running"
        self.update_queue_box()
        self.start_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        current = self._batch_done + self._batch_failed + 1
        self._update_batch_counter()
        self.header_status_var.set(
            f"v{APP_VERSION}  |  Game {current}/{self._batch_total}  |  ✓{self._batch_done} ✗{self._batch_failed}"
        )
        self.status_update(
            f"Game {current}/{self._batch_total}",
            f"Starting: {item.name}",
            "Scanning Files", 0, 0, "00:00", "—", "—"
        )
        self.log("INFO", f"── Batch auto-advance: game {current}/{self._batch_total} — {item.name}")
        self.cancel_requested = False
        self.worker = CLIWorker(self, item, cmd, cwd, out_dir, temp_dir)
        self.worker.start()

    def _show_batch_complete(self):
        total = self._batch_total
        done  = self._batch_done
        fail  = self._batch_failed
        self.batch_counter_var.set(
            f"Batch complete  |  ✓ {done}/{total}  ✗ {fail}/{total}"
        )
        msg = (
            f"Batch compression finished.\n\n"
            f"Total games:  {total}\n"
            f"Successful:   {done}\n"
            f"Failed:       {fail}\n"
        )
        if fail == 0:
            self.log("SUCCESS", f"🏁 Batch complete — all {total} game(s) compressed successfully.")
        else:
            self.log("WARN", f"🏁 Batch complete — {done}/{total} succeeded, {fail} failed.")
        messagebox.showinfo("Batch Complete", msg)

    # ── Start / Cancel ────────────────────────────────────────────────────────
    def start(self):
        if not self.output_var.get().strip():
            messagebox.showerror("Missing output", "Select an output folder.")
            return
        if not self.temp_var.get().strip():
            self.temp_var.set(str(Path(self.output_var.get()) / "_ffpfsc_temp"))
        if not self.queue:
            self.pending_start = True
            self.add_source_to_queue()
            return

        item = self.queue[0]

        # ── Archive placeholder — extract first, then compress ────────────────
        if getattr(item, "archive_path", None):
            self._extract_queued_item(item)
            return

        try:
            cmd, cwd, out_dir, temp_dir = self.build_command(item)
        except Exception as e:
            messagebox.showerror("Cannot start", str(e))
            return

        # Show space diagnostics dialog — opens instantly, drive type detects in background
        diag = SpaceDiagnosticsDialog(self.root, item, temp_dir, out_dir)
        self.root.wait_window(diag)
        if not diag.proceed:
            self.status_update("Ready", "Drive check cancelled.", "Ready", 0, 0, "00:00", "—", "—")
            return

        # Stale temp data warning
        try:
            if temp_dir.exists():
                stale_items = [p for p in temp_dir.iterdir() if p.name.lower().startswith("tmp")]
                if stale_items:
                    stale_size = sum(folder_size(p) for p in stale_items)
                    if stale_size > 1024 * 1024 * 1024:
                        keep_running = messagebox.askyesno(
                            "Temporary data found",
                            f"Found {format_size(stale_size)} of old temporary data in:\n{temp_dir}\n\n"
                            "Continue anyway?\n\nChoose No to manually delete old temp folders first."
                        )
                        if not keep_running:
                            return
        except Exception:
            pass

        # Initialise batch counters on a fresh (non-auto-advance) start
        self._batch_total   = len(self.queue)
        self._batch_done    = 0
        self._batch_failed  = 0
        self._batch_running = self._batch_total > 0
        self._update_batch_counter()

        self._last_cmd_str = " ".join(cmd)
        self.cancel_requested = False
        item.status = "Running"
        self.update_queue_box()
        self.start_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        label = f"Game 1/{self._batch_total}" if self._batch_total > 1 else "Starting"
        self.status_update(label, "Launching backend.", "Starting", 0, 0, "00:00", "—", "—")
        self.worker = CLIWorker(self, item, cmd, cwd, out_dir, temp_dir)
        self.worker.start()

    def cancel(self):
        self.cancel_requested = True
        self.status_update("Cancelling", "Cancel requested.", "Cancelling", 0, 0, "—", "—", "—")

    def status_update(self, title, detail, stage, stage_pct, overall_pct, elapsed, speed, eta):
        if stage == "Creating Temp PFS" and stage_pct >= 100:
            stage_pct = 99
        self.status_q.put((title, detail, stage, stage_pct, overall_pct, elapsed, speed, eta))

    def log(self, tag, msg):
        self.log_q.put((tag, msg))

    def finish(self, success, msg, last_cmd=""):
        self.done_q.put((success, msg, last_cmd))

    def add_history(self, item, output, final_size, elapsed):
        saved = item.size - final_size if item.size and final_size else 0
        pct = saved / item.size * 100 if item.size else 0
        hist = load_history()
        hist.append({
            "date": now_datetime(),
            "name": item.name,
            "title_id": item.title_id,
            "original": item.size,
            "final": final_size,
            "saved": saved,
            "pct": pct,
            "elapsed": elapsed,
            "output": output,
        })
        save_history(hist)
        rating, _ = compression_rating(pct)
        self.saved_var.set(f"Saved: {format_size(saved)}")
        self.ratio_var.set(f"Compression: {pct:.2f}%")
        self.rating_var.set(f"Rating: {rating}")
        self.refresh_history()
        self.refresh_statistics()

    # ── Tools ─────────────────────────────────────────────────────────────────
    def clear_temp_files(self):
        tp = self.temp_var.get().strip()
        if not tp:
            messagebox.showerror("No temp folder", "No temp folder is set.")
            return
        temp_dir = Path(tp)
        if not temp_dir.exists():
            messagebox.showinfo("Clear Temp", "Temp folder does not exist. Nothing to clear.")
            return
        size = get_folder_size(temp_dir)
        if size == 0:
            messagebox.showinfo("Clear Temp", "Temp folder is already empty.")
            return
        ok = messagebox.askyesno(
            "Clear Temp Files",
            f"Delete all contents of:\n{temp_dir}\n\n"
            f"Size to free: {format_size(size)}\n\n"
            "Are you sure? This cannot be undone."
        )
        if not ok:
            return
        try:
            shutil.rmtree(str(temp_dir), ignore_errors=True)
            temp_dir.mkdir(parents=True, exist_ok=True)
            messagebox.showinfo("Clear Temp", f"Temp folder cleared. Freed {format_size(size)}.")
            self.log("OK", f"Temp folder cleared: {temp_dir} ({format_size(size)} freed)")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to clear temp folder:\n{e}")

    def export_diagnostics(self):
        zip_path = export_diagnostic_zip(last_cmd=self._last_cmd_str)
        if zip_path and zip_path.exists():
            ok = messagebox.askyesno(
                "Diagnostic Package",
                f"Diagnostic ZIP saved to:\n{zip_path}\n\nOpen folder?"
            )
            if ok:
                open_path(APP_DIR)
        else:
            messagebox.showerror("Error", "Failed to create diagnostic ZIP.")

    # ── History & Statistics ──────────────────────────────────────────────────
    def refresh_history(self):
        self.history_box.configure(state="normal")
        self.history_box.delete("1.0", "end")
        hist = load_history()
        if not hist:
            self.history_box.insert("end", "No compressions recorded yet.\n")
            self.history_box.configure(state="disabled")
            return
        header = f"{'Date':<20} {'Game':<35} {'Original':>10} {'Output':>10} {'Saved':>10} {'%':>6}  Rating\n"
        self.history_box.insert("end", header)
        self.history_box.insert("end", "─" * len(header) + "\n")
        for entry in reversed(hist[-50:]):
            orig = format_size(entry.get("original", 0))
            final = format_size(entry.get("final", 0))
            saved = format_size(entry.get("saved", 0))
            pct = entry.get("pct", 0)
            rating, _ = compression_rating(pct)
            name = entry.get("name", "Unknown")[:34]
            date = entry.get("date", "")[:19]
            line = f"{date:<20} {name:<35} {orig:>10} {final:>10} {saved:>10} {pct:>5.1f}%  {rating}\n"
            self.history_box.insert("end", line)
        self.history_box.configure(state="disabled")

    def refresh_statistics(self):
        self.stats_box.configure(state="normal")
        self.stats_box.delete("1.0", "end")
        hist = load_history()

        total_games = len(hist)
        total_original = sum(e.get("original", 0) for e in hist)
        total_final = sum(e.get("final", 0) for e in hist)
        total_saved = sum(e.get("saved", 0) for e in hist)
        avg_pct = (sum(e.get("pct", 0) for e in hist) / total_games) if total_games else 0

        lines = [
            f"  Games Compressed:      {total_games}",
            f"  Total Original Size:   {format_size(total_original)}",
            f"  Total Output Size:     {format_size(total_final)}",
            f"  Total Space Saved:     {format_size(total_saved)}",
            f"  Average Compression:   {avg_pct:.1f}%",
            "",
        ]

        if hist:
            best = max(hist, key=lambda e: e.get("pct", 0))
            lines.append(f"  Best Compression:      {best.get('name','?')[:40]}  ({best.get('pct',0):.1f}%)")
            worst = min(hist, key=lambda e: e.get("pct", 0))
            lines.append(f"  Worst Compression:     {worst.get('name','?')[:40]}  ({worst.get('pct',0):.1f}%)")

        for line in lines:
            self.stats_box.insert("end", line + "\n")
        self.stats_box.configure(state="disabled")

    # ── ShadowMount help ──────────────────────────────────────────────────────
    def _show_sm_help(self):
        win = ctk.CTkToplevel(self.root)
        win.title("ShadowMount Compatibility")
        win.configure(fg_color=BLACK)
        win.geometry("480x380")
        win.resizable(False, False)
        win.lift(); win.focus_force(); win.grab_set()
        ctk.CTkLabel(win, text="ℹ  ShadowMount Compatibility",
                      text_color=YELLOW, font=ctk.CTkFont(size=15, weight="bold")
                     ).pack(anchor="w", padx=18, pady=(16, 6))
        ctk.CTkLabel(win,
                      text=(
                          "Output .ffpfsc files are designed for use with ShadowMount,\n"
                          "a PS5 backup manager.\n\n"
                          "To mount a compressed game:\n"
                          "  1.  Copy the .ffpfsc file to your PS5 internal storage\n"
                          "      or an external drive (USB SSD/HDD).\n"
                          "  1a. If you already have a shortcut for this game on the XMB,\n"
                          "      delete it first — the old entry causes a param error and\n"
                          "      the game won't appear after mounting.\n"
                          "  2.  Open ShadowMount on your PS5 and let it scan.\n"
                          "      If the game is not detected or the shortcut is not made,\n"
                          "      re-run ShadowMount.\n"
                          "  3.  Select the game from the XMB and launch it —\n"
                          "      it will appear and run like a standard title.\n\n"
                          "Requirements for full compatibility:\n"
                          "  • sce_sys/param.json must exist in the original dump\n"
                          "  • eboot.bin must exist in the original dump\n\n"
                          "If the game still doesn't appear, verify the dump structure\n"
                          "and try re-compressing."
                      ),
                      text_color=WHITE, font=ctk.CTkFont(size=12),
                      justify="left", anchor="w", wraplength=440
                     ).pack(anchor="w", padx=18, pady=(0, 4))
        ctk.CTkButton(win, text="Close", command=win.destroy,
                       fg_color=GREEN, hover_color=GREEN2, text_color="#061006"
                      ).pack(anchor="e", padx=18, pady=(0, 16))

    # ── Compatibility report ───────────────────────────────────────────────────
    def _prompt_compat_share(self, item, final_size: int = 0):
        """Pop up after a successful compression asking the user to share compat data."""
        if item is None:
            return

        win = ctk.CTkToplevel(self.root)
        win.title("Share Compatibility Data")
        win.configure(fg_color=BLACK)
        win.geometry("480x320")
        win.resizable(False, False)
        win.transient(self.root)
        win.lift()
        win.focus_force()
        win.after(50, win.grab_set)

        ctk.CTkLabel(win, text="🎮  Share Compatibility Report?",
                      font=ctk.CTkFont(size=16, weight="bold"),
                      text_color=GREEN).pack(anchor="w", padx=20, pady=(18, 4))
        ctk.CTkLabel(win,
                      text="Help the community by sharing how well this game compressed.\n"
                           "No personal data is collected — only game info and result.",
                      text_color=MUTED, font=ctk.CTkFont(size=12),
                      justify="left", wraplength=440).pack(anchor="w", padx=20, pady=(0, 12))

        # Summary card
        card = ctk.CTkFrame(win, fg_color=PANEL, corner_radius=8)
        card.pack(fill="x", padx=20, pady=(0, 12))
        rows = [
            ("Game",             item.name),
            ("Title ID",         item.title_id),
            ("Original Size",    format_size(item.size) if item.size else "—"),
            ("Compressed Size",  format_size(final_size) if final_size else "—"),
        ]
        for lbl, val in rows:
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=2)
            ctk.CTkLabel(row, text=lbl + ":", text_color=MUTED,
                          font=ctk.CTkFont(size=11), width=130, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=val, text_color=WHITE,
                          font=ctk.CTkFont(size=11), anchor="w").pack(side="left")

        status_var = tk.StringVar(value="Not Tested Yet")

        status_lbl = ctk.CTkLabel(win, text="", text_color=MUTED,
                                   font=ctk.CTkFont(size=11))
        status_lbl.pack(anchor="w", padx=20)

        def _send():
            import datetime
            report = {
                "game_title":      item.name,
                "title_id":        item.title_id,
                "original_size":   format_size(item.size) if item.size else "",
                "compressed_size": format_size(final_size) if final_size else "",
                "storage":         self._compat_storage_var.get(),
                "shadowmount_ver": self._compat_smver_var.get().strip(),
                "status":          status_var.get(),
                "notes":           "",
                "submitted":       datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            add_compat_report(report)
            self.refresh_compat_list()
            status_lbl.configure(text="⏳ Sending to community…", text_color=YELLOW)
            def _post():
                try:
                    import urllib.request as _ur, json as _js
                    payload = _js.dumps(report).encode()
                    req = _ur.Request(COMMUNITY_URL, data=payload,
                                      headers={"Content-Type": "application/json"})
                    with _ur.urlopen(req, timeout=15) as resp:
                        resp.read()
                    win.after(0, lambda: status_lbl.configure(
                        text="✓ Sent! Thank you for contributing.", text_color=("#1a7a40", "#4ade80")))
                    self.log("OK", f"Compat report sent: {item.name} — {report['status']}")
                    win.after(2000, win.destroy)
                except Exception as e:
                    win.after(0, lambda: status_lbl.configure(
                        text=f"⚠ Send failed: {e}", text_color=RED))
                    self.log("WARN", f"Community share failed: {e}")
            threading.Thread(target=_post, daemon=True).start()

        def _skip():
            win.destroy()

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(8, 16))
        ctk.CTkButton(btn_row, text="✓  Yes, Share Data", fg_color=GREEN,
                       text_color="#061006", hover_color=GREEN2,
                       command=_send).pack(side="left", expand=True, fill="x", padx=(0, 6))
        ctk.CTkButton(btn_row, text="✗  No Thanks", fg_color=CARD2,
                       text_color=WHITE, hover_color=("#b0b0b0", "#2a2a2a"),
                       command=_skip).pack(side="left", expand=True, fill="x", padx=(6, 0))

    def _check_pending_compat_reports(self):
        """On startup: find history entries with no community report and prompt the user."""
        settings = load_settings()
        if settings.get("skip_compat_reminder", False):
            return
        history  = load_history()
        reported = {r.get("title_id", "").strip().upper() for r in load_compat()}
        # Games compressed by this user but never reported
        seen_tids: set[str] = set()
        pending = []
        for h in history:
            tid = h.get("title_id", "").strip().upper()
            if tid and tid not in reported and tid not in seen_tids:
                seen_tids.add(tid)
                pending.append(h)
        if not pending:
            return
        self._show_pending_compat_dialog(pending)

    def _show_pending_compat_dialog(self, pending: list):
        """Small non-modal dialog listing compressed-but-unreported games."""
        win = ctk.CTkToplevel(self.root)
        win.title("Community Reports — Have You Tested These?")
        win.configure(fg_color=BLACK)
        win.geometry("520x420")
        win.resizable(False, True)
        win.transient(self.root)
        win.lift()

        ctk.CTkLabel(win,
                      text="🎮  Have you tested these compressed games on PS5?",
                      font=ctk.CTkFont(size=14, weight="bold"),
                      text_color=GREEN).pack(anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(win,
                      text="The community hasn't received a report for the games below.\n"
                           "If you've tried them with ShadowMount, please share the result — it only takes a second.",
                      text_color=MUTED, font=ctk.CTkFont(size=11),
                      justify="left", wraplength=480).pack(anchor="w", padx=18, pady=(0, 8))

        scroll = ctk.CTkScrollableFrame(win, fg_color=PANEL, corner_radius=6)
        scroll.pack(fill="both", expand=True, padx=18, pady=(0, 8))
        scroll.grid_columnconfigure(0, weight=1)

        STATUS_OPTS = ["Not Tested Yet", "Working", "Partial", "Not Working"]
        row_vars: list[tuple[dict, tk.StringVar]] = []

        for i, h in enumerate(pending[:15]):   # cap at 15 so dialog doesn't get huge
            name  = h.get("name", "Unknown")
            tid   = h.get("title_id", "")
            date  = h.get("date", "")[:10]

            row = ctk.CTkFrame(scroll, fg_color=CARD, corner_radius=6)
            row.grid(row=i, column=0, sticky="ew", pady=3, padx=2)
            row.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(row,
                          text=f"{name}  [{tid}]",
                          text_color=WHITE, font=ctk.CTkFont(size=11, weight="bold"),
                          anchor="w").grid(row=0, column=0, sticky="w", padx=10, pady=(6, 0))
            ctk.CTkLabel(row,
                          text=f"Compressed {date}",
                          text_color=MUTED, font=ctk.CTkFont(size=10),
                          anchor="w").grid(row=1, column=0, sticky="w", padx=10, pady=(0, 4))

            sv = tk.StringVar(value="Not Tested Yet")
            ctk.CTkOptionMenu(row, variable=sv, values=STATUS_OPTS,
                               fg_color=CARD2, button_color=CARD2,
                               dropdown_fg_color=PANEL,
                               text_color=WHITE, font=ctk.CTkFont(size=11),
                               width=160).grid(row=0, column=1, rowspan=2, padx=10, pady=4)
            row_vars.append((h, sv))

        def _submit_all():
            import datetime
            submitted = 0
            for h, sv in row_vars:
                status = sv.get()
                if status == "Not Tested Yet":
                    continue
                report = {
                    "game_title":      h.get("name", "Unknown"),
                    "title_id":        h.get("title_id", ""),
                    "original_size":   format_size(h["original"]) if h.get("original") else "",
                    "compressed_size": format_size(h["final"])    if h.get("final")    else "",
                    "storage":         self._compat_storage_var.get(),
                    "shadowmount_ver": self._compat_smver_var.get().strip(),
                    "status":          status,
                    "notes":           "",
                    "submitted":       datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                }
                add_compat_report(report)
                def _post(r=report):
                    try:
                        import urllib.request as _ur, json as _js
                        payload = _js.dumps(r).encode()
                        req = _ur.Request(COMMUNITY_URL, data=payload,
                                          headers={"Content-Type": "application/json"})
                        with _ur.urlopen(req, timeout=15) as resp:
                            resp.read()
                        self.log("OK", f"Compat report sent: {r['game_title']} — {r['status']}")
                    except Exception as e:
                        self.log("WARN", f"Community share failed: {e}")
                threading.Thread(target=_post, daemon=True).start()
                submitted += 1
            self.refresh_compat_list()
            win.destroy()
            if submitted:
                self.log("OK", f"Submitted {submitted} community report(s). Thank you!")

        def _dont_ask():
            s = load_settings()
            s["skip_compat_reminder"] = True
            save_settings(s)
            win.destroy()

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(fill="x", padx=18, pady=(0, 14))
        ctk.CTkButton(btn_row, text="✓  Submit Selected",
                       fg_color=GREEN, hover_color=GREEN2, text_color="#061006",
                       command=_submit_all).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ctk.CTkButton(btn_row, text="Later",
                       fg_color=CARD2, text_color=WHITE,
                       hover_color=("#b0b0b0","#2a2a2a"),
                       command=win.destroy).pack(side="left", expand=True, fill="x", padx=(4, 4))
        ctk.CTkButton(btn_row, text="Don't Ask Again",
                       fg_color=CARD2, text_color=MUTED,
                       hover_color=("#b0b0b0","#2a2a2a"),
                       command=_dont_ask).pack(side="left", expand=True, fill="x", padx=(4, 0))

    def _compat_autofill(self, item=None, final_size: int = 0):
        """Fill the compatibility form from a completed compression result."""
        try:
            report_text = FINAL_REPORT_FILE.read_text(encoding="utf-8", errors="replace")
        except Exception:
            report_text = ""

        def _grab(key: str) -> str:
            for line in report_text.splitlines():
                if line.lower().startswith(key.lower() + ":"):
                    return line.split(":", 1)[1].strip()
            return ""

        # Prefer the passed item, else fall back to queue[0], else parse report
        src = item or (self.queue[0] if self.queue else None)
        if src:
            self._compat_title_var.set(src.name)
            self._compat_titleid_var.set(src.title_id)
            self._compat_origsize_var.set(format_size(src.size) if src.size else "")
        else:
            self._compat_title_var.set(_grab("Game"))
            self._compat_titleid_var.set(_grab("Title ID"))
            self._compat_origsize_var.set(_grab("Original Size"))

        if final_size:
            self._compat_compsize_var.set(format_size(final_size))
        else:
            comp = _grab("Compressed Size") or _grab("Output Size")
            self._compat_compsize_var.set(comp)

        # Clear notes so user fills in their own experience
        self._compat_notes_box.delete("1.0", "end")

    def submit_compat_report(self):
        title   = self._compat_title_var.get().strip()
        tid     = self._compat_titleid_var.get().strip()
        orig    = self._compat_origsize_var.get().strip()
        comp    = self._compat_compsize_var.get().strip()
        smver   = self._compat_smver_var.get().strip()
        storage = self._compat_storage_var.get()
        status  = self._compat_status_var.get()
        notes   = self._compat_notes_box.get("1.0", "end").strip()

        if not title and not tid:
            messagebox.showerror("Missing data", "Enter at least a Game Title or Title ID.")
            return

        import datetime
        report = {
            "game_title":       title or tid,
            "title_id":         tid,
            "original_size":    orig,
            "compressed_size":  comp,
            "storage":          storage,
            "shadowmount_ver":  smver,
            "status":           status,
            "notes":            notes,
            "submitted":        datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        add_compat_report(report)
        self.log("OK", f"Compatibility report saved: {title or tid} — {status}")
        self.refresh_compat_list()
        self._compat_notes_box.delete("1.0", "end")

        # ── Optionally share to community Google Sheet ────────────────────────
        if getattr(self, "_compat_share_var", None) and self._compat_share_var.get():
            self._compat_share_status.configure(text="⏳ Sending…", text_color=YELLOW)
            def _post():
                try:
                    import urllib.request as _ur, json as _js
                    payload = _js.dumps(report).encode()
                    req = _ur.Request(COMMUNITY_URL, data=payload,
                                      headers={"Content-Type": "application/json"})
                    with _ur.urlopen(req, timeout=15) as resp:
                        resp.read()
                    self.root.after(0, lambda: self._compat_share_status.configure(
                        text="✓ Shared!", text_color=("#1a7a40", "#4ade80")))
                    self.log("OK", f"Compat report shared to community: {title or tid}")
                except Exception as e:
                    self.root.after(0, lambda: self._compat_share_status.configure(
                        text=f"⚠ Failed: {e}", text_color=RED))
                    self.log("WARN", f"Community share failed: {e}")
                self.root.after(6000, lambda: self._compat_share_status.configure(text=""))
            threading.Thread(target=_post, daemon=True).start()

        messagebox.showinfo("Submitted", f"Report saved for: {title or tid}")

    def refresh_compat_list(self):
        reports = load_compat()
        self.compat_box.configure(state="normal")
        self.compat_box.delete("1.0", "end")
        if not reports:
            self.compat_box.insert("end", "No compatibility reports yet.\n\n"
                                           "Use the form to submit one after testing a game with ShadowMount.")
            self.compat_box.configure(state="disabled")
            return

        STATUS_ICON = {"Working": "✅", "Partial": "⚠", "Not Working": "❌"}

        # Group reports by title_id so duplicate submissions for the same game
        # are shown as a single aggregated card instead of N identical rows.
        from collections import OrderedDict
        groups: OrderedDict = OrderedDict()
        for r in reports:
            key = r.get("title_id", "").strip().upper() or r.get("game_title", "Unknown")
            groups.setdefault(key, []).append(r)

        for key, group in groups.items():
            # Use the most recent (first) entry for name / size / meta
            latest = group[0]
            name  = latest.get("game_title", "Unknown")
            tid   = latest.get("title_id", "")
            orig  = latest.get("original_size", "")
            comp  = latest.get("compressed_size", "")
            sizes = f"{orig} → {comp}" if orig and comp else (orig or comp)

            if len(group) == 1:
                # Single report — show full detail as before
                r     = latest
                icon  = STATUS_ICON.get(r.get("status", ""), "❓")
                store = r.get("storage", "")
                smver = r.get("shadowmount_ver", "")
                notes = r.get("notes", "")
                date  = r.get("submitted", "")
                line1 = f"{icon}  {name}"
                if tid:
                    line1 += f"  [{tid}]"
                line2_parts = [p for p in [store, f"SM v{smver}" if smver else "", sizes, date] if p]
                self.compat_box.insert("end", line1 + "\n")
                if line2_parts:
                    self.compat_box.insert("end", f"   {'   '.join(line2_parts)}\n")
                if notes:
                    self.compat_box.insert("end", f"   📝 {notes}\n")
            else:
                # Multiple reports — show aggregated summary
                counts = {}
                for r in group:
                    s = r.get("status", "Unknown")
                    counts[s] = counts.get(s, 0) + 1

                # Pick the overall consensus icon (majority status)
                best = max(counts, key=counts.get)
                icon = STATUS_ICON.get(best, "❓")

                line1 = f"{icon}  {name}"
                if tid:
                    line1 += f"  [{tid}]"
                line1 += f"  ({len(group)} reports)"
                self.compat_box.insert("end", line1 + "\n")

                # Status breakdown
                breakdown = "   ".join(
                    f"{STATUS_ICON.get(s, '❓')} {s}: {n}"
                    for s, n in sorted(counts.items(), key=lambda x: -x[1])
                )
                self.compat_box.insert("end", f"   {breakdown}\n")
                if sizes:
                    self.compat_box.insert("end", f"   {sizes}\n")

                # Show individual notes if any report has them
                for r in group:
                    note = r.get("notes", "").strip()
                    if note:
                        date = r.get("submitted", "")
                        self.compat_box.insert("end", f"   📝 {note}" + (f"  ({date})" if date else "") + "\n")

            self.compat_box.insert("end", "\n")
        self.compat_box.configure(state="disabled")

    def export_compat_csv(self):
        reports = load_compat()
        if not reports:
            messagebox.showinfo("No data", "No compatibility reports to export.")
            return
        path = filedialog.asksaveasfilename(
            title="Export Compatibility List",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="ps5_compat_list.csv",
        )
        if not path:
            return
        import csv
        fields = ["game_title","title_id","original_size","compressed_size",
                  "storage","shadowmount_ver","status","notes","submitted"]
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
                w.writeheader()
                w.writerows(reports)
            messagebox.showinfo("Exported", f"Saved {len(reports)} report(s) to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))

    # ── Sound + Summary ───────────────────────────────────────────────────────
    def play_complete_sound(self, success=True):
        if not winsound:
            return
        try:
            if success and self.sound_complete_var.get():
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            elif not success and self.sound_error_var.get():
                winsound.MessageBeep(winsound.MB_ICONHAND)
        except Exception:
            pass

    def show_summary_popup(self):
        try:
            report = FINAL_REPORT_FILE.read_text(encoding="utf-8", errors="replace")
        except Exception:
            report = "Compression complete."
        report += (
            "\n\nNote: Compression does not improve FPS or graphics quality. "
            "If the rating is POOR, keep the original uncompressed folder instead."
        )
        self._last_result_text = report
        SummaryDialog(self.root, report)

    def copy_last_result(self):
        text = getattr(self, "_last_result_text", "")
        if not text:
            try:
                text = FINAL_REPORT_FILE.read_text(encoding="utf-8", errors="replace")
            except Exception:
                text = ""
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            messagebox.showinfo("Copied", "Compression result copied to clipboard.")

    def open_raw_log(self):
        ensure_app_dir()
        RAW_LOG_FILE.touch(exist_ok=True)
        open_path(RAW_LOG_FILE)

    def open_output_folder(self):
        p = self.output_var.get()
        if p and Path(p).exists():
            open_path(p)

    def clear_logs(self):
        self.log_box.delete("1.0", "end")
        self.visible_log_lines = 0

    # ── Stage display ─────────────────────────────────────────────────────────
    def update_stages_display(self, current_stage, pct):
        full_names   = [s[0] for s in _STAGE_DEFS]
        current_idx  = full_names.index(current_stage) if current_stage in full_names else -1
        for i, (lbl, (full, short)) in enumerate(zip(self._stage_labels, _STAGE_DEFS)):
            if current_idx >= 0 and i < current_idx:
                lbl.configure(text=f"✓ {short}", text_color=("#1a7a40", "#4ade80"))
            elif i == current_idx:
                dp = min(int(pct), 99) if full == "Creating Temp PFS" else int(pct)
                lbl.configure(text=f"▶ {short} {dp}%", text_color=YELLOW)
            else:
                lbl.configure(text=f"○ {short}", text_color=MUTED)

    # ── Poll loop ─────────────────────────────────────────────────────────────
    def _tick_elapsed(self):
        """Called every poll cycle while a worker is live — keeps elapsed ticking
        regardless of whether the backend is printing anything."""
        w = getattr(self, "worker", None)
        if w and w.is_alive() and w.start_time:
            self.elapsed_var.set(f"Elapsed: {format_duration(time.time() - w.start_time)}")

    def _poll(self):
        try:
            self._poll_inner()
        except Exception as e:
            # Last-resort catch — log and keep the loop alive no matter what.
            try:
                self.log("ERROR", f"[_poll crash — loop kept alive] {e}")
            except Exception:
                pass
        self.root.after(200, self._poll)

    def _poll_inner(self):
        self._tick_elapsed()
        try:
            while True:
                status, payload = self.scan_q.get_nowait()
                if status == "ok":
                    item = payload
                    self.queue.append(item)
                    self.update_queue_box(select_item=item)
                    self.status_update("Ready", f"{item.title_id} added to queue.",
                                        "Ready", 0, 0, "00:00", "—", "—")
                    self.log("OK", f"Added {item.title_id} | {item.name} | {format_size(item.size)}")
                    if self.pending_start:
                        self.pending_start = False
                        self.start()

                elif status == "multi_found":
                    # Multiple extracted game folders discovered
                    games: list = payload
                    count = len(games)
                    preview = "\n".join(f"  • {g.name}" for g in games[:10])
                    if count > 10:
                        preview += f"\n  … and {count - 10} more"
                    ok = messagebox.askyesno(
                        f"Found {count} Games",
                        f"Found {count} PS5 game folder(s):\n\n{preview}\n\n"
                        f"Add all {count} to the queue?"
                    )
                    if ok:
                        self.log("INFO", f"Queuing {count} games…")
                        self.status_update("Scanning", f"Adding {count} games to queue…",
                                            "Scanning Files", 0, 0, "00:00", "—", "—")
                        def _add_all(paths=games):
                            for gpath in paths:
                                try:
                                    self.scan_q.put(("ok", GameItem(gpath)))
                                except Exception as e:
                                    self.log("ERROR", f"Skipped {gpath.name}: {e}")
                        threading.Thread(target=_add_all, daemon=True).start()
                    else:
                        self.status_update("Ready", "Batch add cancelled.", "Ready", 0, 0, "00:00", "—", "—")
                        self.pending_start = False

                elif status == "exfat_found":
                    # Multiple .exfat / .ffpkg disk images found — no extraction needed, queue directly
                    image_list: list = payload
                    count = len(image_list)
                    preview = "\n".join(f"  • {f.name}" for f in image_list[:10])
                    if count > 10:
                        preview += f"\n  … and {count - 10} more"
                    ok = messagebox.askyesno(
                        f"Found {count} Disk Image{'s' if count > 1 else ''}",
                        f"Found {count} disk image(s) (.exfat / .ffpkg):\n\n{preview}\n\n"
                        f"Add all {count} to the queue?\n"
                        "(Each image will be compressed directly — no extraction needed.)"
                    )
                    if ok:
                        for img in image_list:
                            item = GameItem.from_exfat(img)
                            self.queue.append(item)
                            lbl = "exFAT" if img.suffix.lower() == ".exfat" else "ffpkg"
                            self.log("OK", f"{lbl} image queued: {img.name}")
                        self.update_queue_box()
                        self.status_update("Ready", f"{count} disk image(s) added to queue.",
                                            "Ready", 0, 0, "00:00", "—", "—")
                    else:
                        self.status_update("Ready", "Image add cancelled.", "Ready", 0, 0, "00:00", "—", "—")
                        self.pending_start = False

                elif status == "archives_found":
                    # Archive files found inside a scanned folder — queue as placeholders
                    archives: list = payload
                    count = len(archives)
                    preview = "\n".join(f"  • {a.name}" for a in archives[:10])
                    if count > 10:
                        preview += f"\n  … and {count - 10} more"
                    ok = messagebox.askyesno(
                        f"Found {count} Archive{'s' if count > 1 else ''}",
                        f"Found {count} archive file(s):\n\n{preview}\n\n"
                        f"Add all {count} to the queue?\n"
                        "(Each archive will be extracted when it is its turn.)"
                    )
                    if ok:
                        for arc in archives:
                            item = GameItem.from_archive(arc)
                            self.queue.append(item)
                            self.log("OK", f"Archive queued: {arc.name}")
                        self.update_queue_box()
                        self.status_update("Ready", f"{count} archive(s) added to queue.",
                                            "Ready", 0, 0, "00:00", "—", "—")
                    else:
                        self.status_update("Ready", "Archive add cancelled.", "Ready", 0, 0, "00:00", "—", "—")
                        self.pending_start = False

                else:  # "error"
                    self.pending_start = False
                    messagebox.showerror("Scan failed", str(payload))
        except queue.Empty:
            pass

        processed = 0
        try:
            t = self.log_box._textbox
            while processed < 50:
                tag, msg = self.log_q.get_nowait()
                line = f"[{now_time()}] [{tag}] {msg}\n"
                t.insert("end", line, (tag,))
                self.visible_log_lines += 1
                processed += 1
        except (queue.Empty, AttributeError):
            if processed == 0:
                try:
                    while processed < 50:
                        tag, msg = self.log_q.get_nowait()
                        self.log_box.insert("end", f"[{now_time()}] [{tag}] {msg}\n")
                        self.visible_log_lines += 1
                        processed += 1
                except queue.Empty:
                    pass
        if processed:
            if self.visible_log_lines > 1500:
                try:
                    self.log_box._textbox.delete("1.0", "300.0")
                except Exception:
                    self.log_box.delete("1.0", "300.0")
                self.visible_log_lines -= 300

            # Smart auto-scroll: only follow the bottom if the user hasn't scrolled up.
            # yview() returns (top_fraction, bottom_fraction). If bottom_fraction is
            # >= 0.98 the scrollbar is at (or very near) the end — keep following.
            # If the user scrolled up, bottom_fraction < 0.98 — leave their position alone.
            try:
                _, bottom = self.log_box._textbox.yview()
                if bottom >= 0.98:
                    self.log_box._textbox.see("end")
            except Exception:
                try:
                    _, bottom = self.log_box.yview()
                    if bottom >= 0.98:
                        self.log_box.see("end")
                except Exception:
                    pass

        try:
            while True:
                title, detail, stage, stage_pct, overall_pct, elapsed, speed, eta = self.status_q.get_nowait()
                self.big_status_var.set(title)
                self.big_detail_var.set(detail)
                self.stage_title_var.set(stage)
                self.stage_detail_var.set(detail)
                self.stage_pct_var.set(f"{int(stage_pct)}%")
                self.overall_pct_var.set(f"{int(overall_pct)}%")
                self.stage_bar.set(max(0, min(1, stage_pct / 100)))
                self.overall_bar.set(max(0, min(1, overall_pct / 100)))
                self.speed_var.set(f"Speed: {speed}")
                self.elapsed_var.set(f"Elapsed: {elapsed}")
                self.eta_var.set(f"ETA: {eta}")
                self.header_status_var.set(f"v{APP_VERSION}  |  Stage: {stage}")
                self.footer_var.set(f"● {title}")
                self.update_stages_display(stage, stage_pct)
        except queue.Empty:
            pass

        # ── Archive extraction completion ─────────────────────────────────────
        try:
            status, payload = self._extract_q.get_nowait()
            if status == "ok":
                item = payload
                # Item was updated in-place — clear cache so details panel refreshes fully
                self._details_item   = None
                self._loaded_art_key = None
                self.update_queue_box(select_item=item)
                self.log("OK", f"Extraction complete: {item.name}  [{format_size(item.size)}]")
                # Continue into compression now that the item has a real path
                self.start()
            else:
                # Extraction failed — re-enable start, show error
                self.start_btn.configure(state="normal")
                self.cancel_btn.configure(state="disabled")
                if self.queue:
                    self.queue[0].status = "Failed"
                    self.update_queue_box()
                messagebox.showerror("Extraction Failed", payload)
        except queue.Empty:
            pass

        try:
            success, msg, last_cmd = self.done_q.get_nowait()
            self._last_cmd_str = last_cmd

            # Mark current game done/failed and pop from queue
            if self.queue:
                self.queue[0].status = "Done" if success else "Failed"
                completed_item = self.queue.pop(0)
            else:
                completed_item = None

            if success:
                self._batch_done += 1
                self.status_update("Complete", msg, "Complete", 100, 100, "—", "—", "—")
                self.log("SUCCESS", msg)
                self.play_complete_sound(True)

                # Auto-fill compatibility form with completed game data
                _final_sz = getattr(self.worker, "final_size", 0) if self.worker else 0
                self._compat_autofill(item=completed_item, final_size=_final_sz)

                # Feature 5: auto-clear temp after success
                if self.auto_clear_temp_var.get():
                    self._auto_clear_temp()

                # Feature 4: batch auto-advance
                if self._batch_running and self.queue:
                    self.update_queue_box()
                    self._refresh_space_for_item(self.queue[0])
                    self.root.after(600, self._batch_auto_start)
                else:
                    self._batch_running = False
                    self.start_btn.configure(state="normal")
                    self.cancel_btn.configure(state="disabled")
                    self.update_queue_box()
                    self._update_batch_counter()
                    if self._batch_total > 1:
                        self._show_batch_complete()
                    else:
                        if self.open_output_var.get():
                            self.open_output_folder()
                        if self.summary_popup_var.get():
                            self.show_summary_popup()

                # Prompt user to share compatibility data
                self.root.after(400, lambda: self._prompt_compat_share(completed_item, _final_sz))
            else:
                self._batch_failed += 1
                self._batch_running = False
                self.start_btn.configure(state="normal")
                self.cancel_btn.configure(state="disabled")
                self.update_queue_box()
                self._update_batch_counter()
                self.status_update("Failed", msg, "Failed", 0, 0, "—", "—", "—")
                self.log("ERROR", msg)
                self.play_complete_sound(False)
                log_lines = get_last_log_lines(50)
                ErrorDialog(self.root, msg, last_cmd, log_lines)
        except queue.Empty:
            pass


if _HAS_DND:
    class _CTkDnD(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)
else:
    _CTkDnD = ctk.CTk


def main():
    ensure_app_dir()
    root = _CTkDnD()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
