#!/Users/bizkut/Downloads/PS5/.venv/bin/python
from __future__ import annotations
import sys

# Intercept if called as mkpfs sub-command in bundled mode
if len(sys.argv) > 1 and sys.argv[1] == "--mkpfs-internal":
    try:
        from mkpfs.cli import cli_mkpfs_main
        sys.exit(cli_mkpfs_main(sys.argv[2:]))
    except Exception as e:
        print(f"[ERROR] Internal MkPFS call failed: {e}", file=sys.stderr)
        sys.exit(1)

import os
import io
import re
import queue
import threading
import subprocess
import shutil
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

try:
    import customtkinter as ctk
except ImportError:
    raise ImportError("GUI requires 'customtkinter'. Install it via: pip install customtkinter")

import cli

PROGRESS_LINE_RE: re.Pattern[str] = re.compile(r"\[(?P<bar>[#-]{4,})\]\s*(?P<pct>\d{1,3})%\s*(?P<label>[^\r\n]*)")

def read_stream_by_lines(stream):
    buffer = []
    while True:
        char = stream.read(1)
        if not char:
            if buffer:
                yield "".join(buffer)
            break
        if char in ('\r', '\n'):
            if buffer:
                yield "".join(buffer)
                buffer = []
        else:
            buffer.append(char)

class GuiLogRedirect(io.TextIOBase):
    """Thread-safe redirector that feeds a Tkinter text widget via a queue."""
    def __init__(self, app: PS5ContainerBuilderApp, tag: str = "info") -> None:
        super().__init__()
        self._app = app
        self._tag = tag

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        self._app.enqueue_log(text, self._tag)
        return len(text)

    def flush(self) -> None:
        pass

class PS5ContainerBuilderApp:
    def __init__(self, root: ctk.CTk):
        self.root = root
        self.log_queue = queue.Queue(maxsize=10000)
        self.progress_queue = queue.Queue(maxsize=10000)
        self.completion_queue = queue.Queue(maxsize=10000)
        self.worker_thread = None
        self.current_process = None
        self.is_closing = False
        self.is_cancelled = False
        self.is_running = False
        
        self.log_after_id = None
        self.progress_after_id = None
        self.completion_after_id = None
        
        self._setup_window()
        self._build_ui()
        self._start_log_polling()
        self._start_progress_polling()
        self._start_completion_polling()

    def _setup_window(self) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.root.title("PS5 PFS Container Builder GUI")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=0)
        self.root.rowconfigure(1, weight=0)
        self.root.rowconfigure(2, weight=0)
        self.root.rowconfigure(3, weight=1)

        self._build_header()
        self._build_fields()
        self._build_progress()
        self._build_log_console()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.root)
        header.grid(row=0, column=0, padx=12, pady=(12, 6), sticky="ew")
        
        title_label = ctk.CTkLabel(
            header, 
            text="PS5 PFS Container Builder", 
            font=ctk.CTkFont(size=22, weight="bold")
        )
        title_label.pack(side="left", padx=15, pady=10)
        
        subtitle_label = ctk.CTkLabel(
            header,
            text="Compress game folders or exFAT images into ShadowMountPlus .ffpfsc containers",
            font=ctk.CTkFont(size=12, slant="italic"),
            text_color="#94a3b8"
        )
        subtitle_label.pack(side="left", padx=(10, 15), pady=10)

    def _build_fields(self) -> None:
        fields_frame = ctk.CTkFrame(self.root)
        fields_frame.grid(row=1, column=0, padx=12, pady=6, sticky="ew")
        fields_frame.columnconfigure(1, weight=1)
        
        # Source Path
        ctk.CTkLabel(fields_frame, text="Source path:", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=12, pady=10, sticky="e"
        )
        self.source_var = tk.StringVar()
        self.source_entry = ctk.CTkEntry(
            fields_frame, 
            textvariable=self.source_var,
            placeholder_text="Select a game folder or an existing .exfat file"
        )
        self.source_entry.grid(row=0, column=1, padx=6, pady=10, sticky="ew")
        
        self.source_var.trace_add("write", self._on_source_changed)
        
        source_buttons = ctk.CTkFrame(fields_frame, fg_color="transparent")
        source_buttons.grid(row=0, column=2, padx=12, pady=10, sticky="w")
        
        browse_folder_btn = ctk.CTkButton(
            source_buttons, 
            text="Browse Folder", 
            width=110,
            command=self._browse_folder
        )
        browse_folder_btn.pack(side="left", padx=3)
        
        browse_file_btn = ctk.CTkButton(
            source_buttons, 
            text="Browse File", 
            width=110,
            command=self._browse_file
        )
        browse_file_btn.pack(side="left", padx=3)
        
        # Output Destination
        ctk.CTkLabel(fields_frame, text="Output destination:", font=ctk.CTkFont(weight="bold")).grid(
            row=1, column=0, padx=12, pady=10, sticky="e"
        )
        self.output_var = tk.StringVar()
        self.output_entry = ctk.CTkEntry(
            fields_frame, 
            textvariable=self.output_var,
            placeholder_text="Optional: output directory or specific file path (defaults to current directory)"
        )
        self.output_entry.grid(row=1, column=1, padx=6, pady=10, sticky="ew")
        
        browse_out_btn = ctk.CTkButton(
            fields_frame, 
            text="Browse Destination", 
            width=120,
            command=self._browse_destination
        )
        browse_out_btn.grid(row=1, column=2, padx=12, pady=10, sticky="w")
        
        # Password Field (Hidden by default)
        self.password_label = ctk.CTkLabel(fields_frame, text="Password:", font=ctk.CTkFont(weight="bold"))
        self.password_var = tk.StringVar()
        self.password_entry = ctk.CTkEntry(
            fields_frame, 
            textvariable=self.password_var,
            show="*",
            placeholder_text="Archive Password (if any)"
        )
        
        # Options Row
        self.options_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
        self.options_frame.grid(row=2, column=1, columnspan=2, padx=6, pady=6, sticky="w")
        
        self.keep_pfs_var = tk.BooleanVar(value=False)
        self.keep_pfs_checkbox = ctk.CTkCheckBox(
            self.options_frame, 
            text="Keep intermediate nested PFS image (folders only)", 
            variable=self.keep_pfs_var
        )
        self.keep_pfs_checkbox.pack(side="left", padx=10)
        
        self.batch_var = tk.BooleanVar(value=False)
        self.batch_checkbox = ctk.CTkCheckBox(
            self.options_frame, 
            text="Batch Mode (process all subfolders/exfat files)", 
            variable=self.batch_var
        )
        self.batch_checkbox.pack(side="left", padx=10)

    def _build_progress(self) -> None:
        self.progress_frame = ctk.CTkFrame(self.root)
        self.progress_frame.grid(row=2, column=0, padx=12, pady=6, sticky="ew")
        self.progress_frame.columnconfigure(0, weight=1)
        
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ctk.CTkProgressBar(
            self.progress_frame, 
            variable=self.progress_var, 
            mode="determinate"
        )
        self.progress_bar.set(0.0)
        self.progress_bar.grid(row=0, column=0, padx=12, pady=(12, 6), sticky="ew")
        
        self.progress_label = ctk.CTkLabel(
            self.progress_frame, 
            text="Ready",
            font=ctk.CTkFont(size=12)
        )
        self.progress_label.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="w")
        
        buttons_frame = ctk.CTkFrame(self.progress_frame, fg_color="transparent")
        buttons_frame.grid(row=0, column=1, rowspan=2, padx=12, pady=12, sticky="e")
        
        self.action_btn = ctk.CTkButton(
            buttons_frame, 
            text="Pack / Convert", 
            font=ctk.CTkFont(weight="bold"),
            command=self._on_action,
            width=150,
            height=35
        )
        self.action_btn.pack(side="left", padx=5)
        
        self.cancel_btn = ctk.CTkButton(
            buttons_frame, 
            text="Cancel", 
            command=self._on_cancel,
            width=100,
            height=35,
            state="disabled"
        )
        self.cancel_btn.pack(side="left", padx=5)

    def _build_log_console(self) -> None:
        log_frame = ctk.CTkFrame(self.root)
        log_frame.grid(row=3, column=0, padx=12, pady=(6, 12), sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.log_text = ctk.CTkTextbox(
            log_frame,
            wrap="word",
            font=ctk.CTkFont(family="Courier", size=11)
        )
        self.log_text.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")
        self.log_text.configure(state="disabled")
        
        # Colors configure
        self.log_text._textbox.tag_config("header", foreground="#38bdf8", font=("Courier", 11, "bold"))
        self.log_text._textbox.tag_config("section", foreground="#c084fc", font=("Courier", 11, "bold"))
        self.log_text._textbox.tag_config("success", foreground="#34d399")
        self.log_text._textbox.tag_config("warning", foreground="#fbbf24")
        self.log_text._textbox.tag_config("error", foreground="#f87171", font=("Courier", 11, "bold"))
        self.log_text._textbox.tag_config("info", foreground="#cbd5e1")

    def _on_source_changed(self, *args) -> None:
        src = self.source_var.get().lower()
        # Supported archive extensions from mkpfs
        if any(src.endswith(ext) for ext in (".zip", ".rar", ".r00", ".001", "part1.rar")):
            self.password_label.grid(row=2, column=0, padx=12, pady=10, sticky="e")
            self.password_entry.grid(row=2, column=1, padx=6, pady=10, sticky="w")
            self.options_frame.grid(row=3, column=1, columnspan=2, padx=6, pady=6, sticky="w")
        else:
            self.password_label.grid_forget()
            self.password_entry.grid_forget()
            self.password_var.set("")
            self.options_frame.grid(row=2, column=1, columnspan=2, padx=6, pady=6, sticky="w")

    def _browse_folder(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self.source_var.set(path)
            
    def _browse_file(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[
                ("exFAT files", "*.exfat"),
                ("ZIP files", "*.zip"),
                ("RAR files", "*.rar"),
                ("RAR parts", "*.r00"),
                ("001 files", "*.001"),
                ("All files", "*.*"),
            ]
        )
        if path:
            self.source_var.set(path)
            
    def _browse_destination(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self.output_var.set(path)

    def enqueue_log(self, text: str, tag: str = "info") -> None:
        for match in PROGRESS_LINE_RE.finditer(text):
            percent = max(0, min(int(match.group("pct")), 100))
            label = match.group("label").strip() or "Processing"
            try:
                self.progress_queue.put_nowait((percent / 100, label))
            except queue.Full:
                pass
        log_text = PROGRESS_LINE_RE.sub("", text.replace("\r", "\n"))
        if log_text.strip():
            try:
                self.log_queue.put_nowait((log_text, tag))
            except queue.Full:
                pass

    def _start_log_polling(self) -> None:
        self._poll_log_queue()

    def _start_progress_polling(self) -> None:
        self._poll_progress_queue()

    def _start_completion_polling(self) -> None:
        self._poll_completion_queue()

    def _poll_log_queue(self) -> None:
        if self.is_closing:
            return
        chunks = []
        try:
            while True:
                chunks.append(self.log_queue.get_nowait())
        except queue.Empty:
            pass
        if chunks:
            for text, tag in chunks:
                self._append_log(text, tag)
        self.log_after_id = self.root.after(100, self._poll_log_queue)

    def _poll_progress_queue(self) -> None:
        if self.is_closing:
            return
        latest = None
        try:
            while True:
                latest = self.progress_queue.get_nowait()
        except queue.Empty:
            pass
        if latest is not None:
            value, label = latest
            self.progress_var.set(value)
            self.progress_label.configure(text=f"{label} ({int(value * 100)}%)")
        self.progress_after_id = self.root.after(100, self._poll_progress_queue)

    def _poll_completion_queue(self) -> None:
        if self.is_closing:
            return
        completed_info = None
        try:
            while True:
                completed_info = self.completion_queue.get_nowait()
        except queue.Empty:
            pass
        if completed_info is not None:
            name, is_success = completed_info
            self._on_worker_done(name, is_success)
        self.completion_after_id = self.root.after(100, self._poll_completion_queue)

    def _append_log(self, text: str, source_tag: str = "info") -> None:
        self.log_text.configure(state="normal")
        lines = text.split("\n")
        for i, line in enumerate(lines):
            suffix = "\n" if i < len(lines) - 1 else ""
            stripped = line.strip()

            if stripped.startswith("===") or stripped.endswith("==="):
                self.log_text.insert("end", line + suffix, "header")
            elif stripped in (
                "PFS Image Builder - Parameters",
                "Build Summary",
                "PFS Check Report",
                "Build Details",
            ):
                self.log_text.insert("end", line + suffix, "section")
            elif any(term in line.lower() for term in ("error:", "failed", "exception", "failed:", "builderror", "unsupported")):
                self.log_text.insert("end", line + suffix, "error")
            elif any(term in line.lower() for term in ("warning", "warn", "stale")):
                self.log_text.insert("end", line + suffix, "warning")
            elif any(term in line.lower() for term in ("successfully", "completed", "passed")):
                self.log_text.insert("end", line + suffix, "success")
            elif source_tag == "error":
                self.log_text.insert("end", line + suffix, "error")
            else:
                self.log_text.insert("end", line + suffix, "info")

        self.log_text.configure(state="disabled")
        self.log_text.see("end")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _on_action(self) -> None:
        if self.is_running:
            return
            
        self._clear_log()
        self.is_cancelled = False
        self.is_running = True
        self.action_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()
        self.progress_label.configure(text="Initializing pack process...")

        self.worker_thread = threading.Thread(target=self._run_pack_worker, daemon=True)
        self.worker_thread.start()

    def _run_pack_worker(self) -> None:
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = GuiLogRedirect(self, "info")
        sys.stderr = GuiLogRedirect(self, "error")
        is_success = False

        try:
            is_success = self._do_pack_work()
        except Exception as e:
            print(f"[ERROR] Unhandled exception in worker: {e}")
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            try:
                self.completion_queue.put_nowait(("Pack Process", is_success and not self.is_cancelled))
            except queue.Full:
                pass

    def _do_pack_work(self) -> bool:
        source = self.source_var.get().strip()
        output = self.output_var.get().strip()
        keep_pfs = self.keep_pfs_var.get()
        batch = self.batch_var.get()
        password = self.password_var.get()

        if not source:
            print("[ERROR] Source path must be specified.")
            return False

        source_path = Path(source).resolve()
        if not source_path.exists():
            print(f"[ERROR] Source path does not exist: {source_path}")
            return False

        # Prepare outputs
        ffpfs_path = Path(output).resolve() if output else Path(".").resolve()

        # Locate MkPFS
        mkpfs_cmd_base = None
        mkpfs_cwd = None

        if getattr(sys, "frozen", False):
            mkpfs_cmd_base = [sys.executable, "--mkpfs-internal"]
            mkpfs_cwd = None
            print("[INFO] Running in packaged/frozen environment. Using internal MkPFS bundle.")

        # 1. Prioritize any local workspace found in sibling folders containing a mkpfs package
        if mkpfs_cmd_base is None:
            parent_dir = Path(__file__).resolve().parent.parent
            try:
                for sibling in parent_dir.iterdir():
                    if sibling.is_dir() and (sibling / "mkpfs" / "__main__.py").is_file():
                        mkpfs_cmd_base = [sys.executable, "-m", "mkpfs"]
                        mkpfs_cwd = str(sibling)
                        print(f"[INFO] Using local workspace directory at {sibling}")
                        break
            except Exception:
                pass

        # 2. Try system PATH
        if mkpfs_cmd_base is None and shutil.which("mkpfs"):
            mkpfs_cmd_base = ["mkpfs"]

        # 3. Auto-install via pip if not found
        if mkpfs_cmd_base is None:
            print("[INFO] MkPFS not found. Installing automatically via pip...")
            res = subprocess.run([sys.executable, "-m", "pip", "install", "mkpfs"], capture_output=True, text=True)
            if res.returncode != 0:
                print("[ERROR] Failed to install mkpfs. Please install it manually.")
                return False
            print("[OK] MkPFS installed successfully.")
            mkpfs_cmd_base = [sys.executable, "-m", "mkpfs"]

        # Handle Archives directly (no external binary dependencies)
        _is_zip = lambda p: p.name.lower().endswith(".zip")
        _is_rar = lambda p: any(p.name.lower().endswith(ext) for ext in (".rar", ".r00"))
        is_archive = _is_zip(source_path) or _is_rar(source_path)
        
        import contextlib
        @contextlib.contextmanager
        def prepare_source_path(path: Path):
            if _is_zip(path):
                import tempfile, zipfile
                with tempfile.TemporaryDirectory() as tmpdir:
                    try:
                        with zipfile.ZipFile(path) as zf:
                            for member in zf.infolist():
                                dest = Path(tmpdir) / member.filename
                                try:
                                    dest.resolve().relative_to(Path(tmpdir).resolve())
                                except ValueError:
                                    print(f"[ERROR] ZIP path traversal detected: {member.filename}")
                                    raise
                            zf.extractall(tmpdir, pwd=password.encode() if password else None)
                        yield Path(tmpdir)
                    except (zipfile.BadZipFile, RuntimeError) as exc:
                        print(f"[ERROR] ZIP extraction failed: {exc}")
                        raise
            elif _is_rar(path):
                import tempfile
                from unrar import rarfile
                with tempfile.TemporaryDirectory() as tmpdir:
                    try:
                        with rarfile.RarFile(path, pwd=password) as rf:
                            rf.extractall(tmpdir)
                        yield Path(tmpdir)
                    except rarfile.RarWrongPassword:
                        print("[ERROR] RAR extraction failed: wrong or missing password")
                        raise
                    except rarfile.BadRarFile as exc:
                        print(f"[ERROR] RAR extraction failed: {exc}")
                        raise
                    except Exception as exc:
                        print(f"[ERROR] Failed to extract archive: {exc}")
                        raise
            else:
                yield path

        try:
            with prepare_source_path(source_path) as active_source_path:
                # Discover items using cli logic
                try:
                    game_items = cli.find_game_items(active_source_path, batch)
                except SystemExit:
                    print("[ERROR] Discovery failed. Check source directory settings.")
                    return False

                if batch:
                    if not ffpfs_path.exists():
                        ffpfs_path.mkdir(parents=True, exist_ok=True)
                    elif not ffpfs_path.is_dir():
                        print(f"[ERROR] Output path {ffpfs_path} must be a directory when using --batch.")
                        return False

                ext = ".ffpfsc"
                success = True

                for item in game_items:
                    if self.is_cancelled:
                        break
                        
                    title_id = cli.get_title_id(item)
                    if batch or ffpfs_path.is_dir():
                        current_ffpfs_path = ffpfs_path / f"{title_id}{ext}"
                    else:
                        current_ffpfs_path = ffpfs_path.with_suffix(ext)

                    if batch:
                        print(f"\n=== Processing batch item: {title_id} ({item.name}) ===\n")

                    if current_ffpfs_path.exists():
                        print(f"[WARN] Output file already exists: {current_ffpfs_path}")
                        if self.ask_overwrite_confirmation(current_ffpfs_path):
                            print(f"[INFO] Overwriting existing file: {current_ffpfs_path}")
                            try:
                                current_ffpfs_path.unlink()
                            except Exception as e:
                                print(f"[ERROR] Failed to remove existing output file: {e}")
                                return False
                        else:
                            print(f"[INFO] Skipping: {current_ffpfs_path.name}")
                            continue

                    if item.is_file() and item.suffix.lower() == '.exfat':
                        # Direct exFAT to ffpfsc
                        success = self.run_command_stream(
                            mkpfs_cmd_base + ["pack", "file", "--compress", "--version", "PS5", "--inode-bits", "32", str(item), str(current_ffpfs_path)],
                            cwd=mkpfs_cwd
                        )
                    else:
                        # Game folder packing
                        with tempfile.TemporaryDirectory() as temp_dir:
                            temp_pfs = Path(temp_dir) / "pfs_image.dat"

                            # 1. Uncompressed PFS build
                            print(f"[INFO] Packing folder {item.name} to uncompressed PFS image...")
                            success = self.run_command_stream(
                                mkpfs_cmd_base + ["pack", "folder", "--no-compress", "--no-adjust-output-file-extension", "--version", "PS5", "--inode-bits", "32", "--verify", str(item), str(temp_pfs)],
                                cwd=mkpfs_cwd
                            )
                            
                            if not success or self.is_cancelled:
                                break

                            # 2. Compression to .ffpfsc
                            print(f"[INFO] Compressing nested PFS image to outer container {current_ffpfs_path.name}...")
                            success = self.run_command_stream(
                                mkpfs_cmd_base + ["pack", "file", "--compress", "--version", "PS5", "--inode-bits", "32", str(temp_pfs), str(current_ffpfs_path)],
                                cwd=mkpfs_cwd
                            )

                            if not success or self.is_cancelled:
                                break

                            if keep_pfs:
                                saved_pfs_path = current_ffpfs_path.parent / f"{title_id}_nested_pfs.dat"
                                print(f"[INFO] Saving intermediate PFS image to {saved_pfs_path}...")
                                try:
                                    shutil.copy2(temp_pfs, saved_pfs_path)
                                except Exception as e:
                                    print(f"[WARN] Failed to copy intermediate image: {e}")

                    if not success:
                        break

                return success and not self.is_cancelled
        except Exception as e:
            print(f"[ERROR] Exception during packing: {e}")
            import traceback
            traceback.print_exc()
            return False

    def run_command_stream(self, cmd: list[str], cwd: str | None = None) -> bool:
        print(f"[INFO] Running: {' '.join(cmd)}")
        try:
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=cwd
            )
            
            for line in read_stream_by_lines(self.current_process.stdout):
                print(line)
                
            code = self.current_process.wait()
            self.current_process = None
            return code == 0
        except Exception as e:
            print(f"[ERROR] Subprocess execution failed: {e}")
            self.current_process = None
            return False

    def _on_cancel(self) -> None:
        self.is_cancelled = True
        self.progress_label.configure(text="Cancelling...")
        if self.current_process:
            print("\n[WARN] Cancelling... terminating subprocess.\n")
            self.current_process.terminate()
        self.cancel_btn.configure(state="disabled")

    def ask_overwrite_confirmation(self, path: Path) -> bool:
        """Thread-safe way to ask for overwrite confirmation via a messagebox."""
        if threading.current_thread() is threading.main_thread():
            return messagebox.askyesno(
                "Overwrite?",
                f"File '{path.name}' already exists.\nDo you want to overwrite it?"
            )
        
        # We are on a background thread. Schedule on the main thread and wait.
        result = [False]
        event = threading.Event()
        
        def ask():
            res = messagebox.askyesno(
                "Overwrite?",
                f"File '{path.name}' already exists.\nDo you want to overwrite it?"
            )
            result[0] = res
            event.set()
            
        self.root.after(0, ask)
        event.wait()
        return result[0]

    def _on_worker_done(self, name: str, is_success: bool) -> None:
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self.progress_var.set(1.0)
        self.is_running = False
        self.action_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self.worker_thread = None

        if self.is_cancelled:
            self.progress_label.configure(text="Cancelled")
            messagebox.showinfo("Cancelled", "The operation was successfully cancelled.")
        elif is_success:
            self.progress_label.configure(text="Success")
            messagebox.showinfo("Success", "Operation completed successfully!")
        else:
            self.progress_label.configure(text="Failed")
            messagebox.showerror("Error", "Operation finished with errors.\nCheck the log console for details.")

    def _on_close(self) -> None:
        self.is_closing = True
        if self.current_process:
            try:
                self.current_process.terminate()
            except Exception:
                pass
        for after_id in (self.log_after_id, self.progress_after_id, self.completion_after_id):
            if after_id is not None:
                try:
                    self.root.after_cancel(after_id)
                except Exception:
                    pass
        self.root.destroy()

if __name__ == "__main__":
    root = ctk.CTk()
    app = PS5ContainerBuilderApp(root)
    root.mainloop()
