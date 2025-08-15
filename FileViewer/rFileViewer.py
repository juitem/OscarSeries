#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
File Tree + Preview (Markdown/HTML/CSV/TXT)
- Left: Lazy-loaded file tree
- Right: Preview pane with HtmlFrame (tkinterweb) if available, else Text fallback
- Top toolbar: Open Folder, Viewable only (directories always visible), Search
- Status bar at bottom
- CLI: --start-dir, --search
"""

import os
import sys
import csv
import re  # NEW: regex search
from pathlib import Path  # NEW: build file:// URIs for images
import base64  # NEW: encode images for clipboard
import mimetypes  # NEW: detect image mime types
import threading
import io  # NEW: in-memory bytes
import subprocess  # NEW: for Linux xclip fallback
import webbrowser  # NEW: open shared dir in external browser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

import socket  # NEW: check free ports
import atexit  # NEW: cleanup on process exit
import signal  # NEW: signal-based shutdown (POSIX)

# Optional HTML viewer
try:
    from tkinterweb import HtmlFrame  # pip install tkinterweb
except Exception:
    HtmlFrame = None

# ---------- Supported extensions & icons ----------
MD_EXTS   = {".md", ".mdx", ".markdown"}
HTML_EXTS = {".html", ".htm"}
CSV_EXTS  = {".csv"}
TXT_EXTS  = {".txt"}
IMG_EXTS  = {".png", ".jpg", ".jpeg"}  # NEW: images

ICON_MD   = "📝"
ICON_HTML = "🌐"
ICON_CSV  = "📊"
ICON_TXT  = "📄"
ICON_IMG  = "🖼️"  # NEW
ICON_DIR_SHARED = "📡"  # NEW: mark directories that are being shared

VIEWABLE_EXTS = MD_EXTS | HTML_EXTS | CSV_EXTS | TXT_EXTS | IMG_EXTS


# ---------- HTML loader compatibility wrapper ----------
def htmlframe_set(frame, html: str, base_url: str | None = None):
    """
    Try multiple APIs to show HTML in tkinterweb (or compatible widgets).
    Fallback: treat the target as a Text widget and dump HTML source.
    """
    # tkinterweb.HtmlFrame path
    if hasattr(frame, "load_html"):
        if base_url:
            try:
                frame.load_html(html, baseurl=base_url)  # common signature
                return
            except TypeError:
                # Some versions do not accept baseurl kwarg
                try:
                    frame.load_html(html)
                    return
                except Exception:
                    pass
            except Exception:
                try:
                    frame.load_html(html)
                    return
                except Exception:
                    pass
        else:
            try:
                frame.load_html(html)
                return
            except Exception:
                pass

    # Generic widget APIs sometimes seen in alternatives
    for m in ("set_html", "set_content"):
        if hasattr(frame, m):
            try:
                getattr(frame, m)(html)
                return
            except Exception:
                pass

    # Fallback to Text widget style
    try:
        frame.config(state="normal")
        frame.delete("1.0", "end")
        frame.insert("1.0", html)
        frame.config(state="disabled")
    except Exception:
        pass


# ---------- Markdown -> HTML with table support ----------
def render_markdown_to_html(md_text: str) -> tuple[str, str]:
    """
    Convert Markdown text to HTML. Returns (html, engine_name).
    """
    # Preferred: markdown2 (rich extras)
    try:
        import markdown2  # pip install markdown2
        html = markdown2.markdown(
            md_text,
            extras=["tables", "fenced-code-blocks", "strike", "toc", "cuddled-lists"]
        )
        return html, "markdown2"
    except Exception:
        pass

    # Fallback: Python-Markdown
    try:
        import markdown as md  # pip install markdown
        html = md.markdown(
            md_text,
            extensions=["extra", "tables", "fenced_code", "toc", "sane_lists", "admonition", "md_in_html"]
        )
        return html, "python-markdown"
    except Exception:
        from html import escape
        return f"<pre>{escape(md_text)}</pre>", "raw-pre"


# ---------- Utility helpers ----------
def is_viewable_file(path: str) -> bool:
    _, ext = os.path.splitext(path.lower())
    return ext in VIEWABLE_EXTS


def decorate_name(name: str, path: str, is_dir: bool) -> str:
    """Return label with icon for known file types."""
    if is_dir:
        return name
    _, ext = os.path.splitext(path.lower())
    if ext in MD_EXTS:
        return f"{ICON_MD} {name}"
    if ext in HTML_EXTS:
        return f"{ICON_HTML} {name}"
    if ext in CSV_EXTS:
        return f"{ICON_CSV} {name}"
    if ext in TXT_EXTS:
        return f"{ICON_TXT} {name}"
    if ext in IMG_EXTS:
        return f"{ICON_IMG} {name}"
    return name

# ---------- Port utilities ----------
import socket  # ensure available (already imported above)

def is_port_available(port: int) -> bool:
    """Return True if TCP port is free on 0.0.0.0."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("", int(port)))
            return True
        except OSError:
            return False


def find_next_free_port(start: int = 8000, limit: int = 1000) -> int:
    """Find the next available TCP port starting from `start` (inclusive)."""
    p = max(1, int(start))
    for _ in range(max(1, limit)):
        if is_port_available(p):
            return p
        p += 1
    raise RuntimeError("No free port found in range")


# ---------- Tk app ----------
class App(tk.Tk):
    def __init__(self, start_dir: str | None = None, initial_search: str | None = None, visible_only: bool = True, kill_on_terminate: str = "ask"):
        super().__init__()
        self.title("Tree + Preview (MD/HTML/CSV/TXT)")
        self.geometry("1280x860")

        self.status = tk.StringVar(value="Ready.")
        self._build_ui()

        self._last_html = None
        self._last_plain = None
        self._shares: dict[str, tuple[int, subprocess.Popen]] = {}
        # Default share script (can be changed via toolbar button)
        self.share_script_path = os.path.join(os.path.dirname(__file__), "share.py")
        # Last used port for share.py suggestions (set to 7999 so first proposal is 8000)
        self.last_share_port = 7999

        # Apply initial visible-only toggle (from CLI or default)
        self.show_only_viewable.set(bool(visible_only))

        # Initial directory
        self.root_dir = None
        if start_dir:
            self.load_root(start_dir)
        else:
            self.load_root(os.getcwd())

        # Apply initial search if provided
        if isinstance(initial_search, str) and initial_search.strip():
            self.search_var.set(initial_search)
            self.apply_search()  # immediate

        # Ensure initial filter state is applied to current tree contents
        self._apply_viewable_filter()

        # Kill-on-terminate preference: "true" | "false" | "ask"
        self.kill_on_terminate = (kill_on_terminate or "ask").lower()

        # Window close → ask/obey setting
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Only auto-kill at atexit if preference is explicit true (no UI possible at atexit)
        if self.kill_on_terminate == "true":
            atexit.register(self._shutdown_shares)

        # Signals (SIGINT Ctrl+C, SIGTERM) → schedule confirm dialog in UI thread
        def _sig_handler(_sig, _frm):
            try:
                self.after(0, lambda: self._confirm_and_shutdown(source="signal"))
            except Exception:
                # Fallback: hard exit if UI is unavailable
                try:
                    if self.kill_on_terminate == "true":
                        self._shutdown_shares()
                finally:
                    os._exit(0)
        try:
            signal.signal(signal.SIGTERM, _sig_handler)
        except Exception:
            pass
        try:
            signal.signal(signal.SIGINT, _sig_handler)
        except Exception:
            pass
    def _confirm_and_shutdown(self, source: str = "window"):
        """Confirm whether to stop share servers on exit, according to preference, then exit."""
        choice = self.kill_on_terminate
        stop = False
        if choice == "true":
            stop = True
        elif choice == "false":
            stop = False
        else:
            # ask, but only if there are active shares
            if self._shares:
                try:
                    ans = messagebox.askyesno(
                        title="Exit",
                        message="Also stop the share servers on exit?",
                        parent=self
                    )
                except Exception:
                    ans = False
                stop = bool(ans)
            else:
                stop = False
        if stop:
            try:
                self._shutdown_shares()
            except Exception:
                pass
        try:
            self.destroy()
        except Exception:
            os._exit(0)

    def _on_close(self):
        """WM_DELETE_WINDOW handler."""
        self._confirm_and_shutdown(source="window")

    def _shutdown_shares(self, force: bool = False):
        """Terminate all running share subprocesses started by this app."""
        items = list(self._shares.items())
        for dir_path, (port, proc) in items:
            try:
                if proc.poll() is None:
                    if not (sys.platform.startswith("win") or os.name == "nt"):
                        try:
                            os.killpg(proc.pid, signal.SIGTERM)
                        except Exception:
                            proc.terminate()
                    else:
                        proc.terminate()
                    try:
                        proc.wait(timeout=2.0)
                    except Exception:
                        if force:
                            try:
                                if not (sys.platform.startswith("win") or os.name == "nt"):
                                    os.killpg(proc.pid, signal.SIGKILL)
                                else:
                                    proc.kill()
                            except Exception:
                                pass
                        else:
                            try:
                                proc.kill()
                            except Exception:
                                pass
            finally:
                try:
                    self._update_dir_icon(dir_path)
                except Exception:
                    pass
                self._shares.pop(dir_path, None)

    # ---------- UI ----------
    def _build_ui(self):
        # Top toolbar
        top = ttk.Frame(self)
        top.pack(fill=tk.X, side=tk.TOP, padx=8, pady=6)

        ttk.Button(top, text="Open Folder", command=self.choose_folder).pack(side=tk.LEFT)

        self.show_only_viewable = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            top,
            text="Viewable only",
            variable=self.show_only_viewable,
            command=self._apply_viewable_filter  # in-place filter (preserves state)
        ).pack(side=tk.LEFT, padx=(12, 6))

        # Per-extension visibility toggles (icons)
        self.ft_md  = tk.BooleanVar(value=True)
        self.ft_html= tk.BooleanVar(value=True)
        self.ft_csv = tk.BooleanVar(value=True)
        self.ft_txt = tk.BooleanVar(value=True)
        self.ft_png = tk.BooleanVar(value=True)   # NEW
        self.ft_jpg = tk.BooleanVar(value=True)   # NEW (covers .jpg/.jpeg)
        ttk.Checkbutton(top, text="📝",  variable=self.ft_md,   command=self._apply_viewable_filter).pack(side=tk.LEFT, padx=(2, 0))
        ttk.Checkbutton(top, text="🌐",  variable=self.ft_html, command=self._apply_viewable_filter).pack(side=tk.LEFT, padx=(2, 0))
        ttk.Checkbutton(top, text="📊",  variable=self.ft_csv,  command=self._apply_viewable_filter).pack(side=tk.LEFT, padx=(2, 0))
        ttk.Checkbutton(top, text="📄",  variable=self.ft_txt,  command=self._apply_viewable_filter).pack(side=tk.LEFT, padx=(2, 0))
        ttk.Checkbutton(top, text="🖼️PNG", variable=self.ft_png, command=self._apply_viewable_filter).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Checkbutton(top, text="🖼️JPG", variable=self.ft_jpg, command=self._apply_viewable_filter).pack(side=tk.LEFT, padx=(2, 8))

        # Directory refresh icon
        ttk.Button(top, text="🔄", width=3, command=self.refresh_current_dir).pack(side=tk.LEFT, padx=(0, 10))

        # Choose custom share.py script
        ttk.Button(top, text="Share Script…", command=self._choose_share_script).pack(side=tk.LEFT, padx=(0, 10))

        # Search box
        ttk.Label(top, text="Search:").pack(side=tk.LEFT, padx=(12, 6))
        self.search_var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.search_var, width=40)
        entry.pack(side=tk.LEFT)
        entry.bind("<KeyRelease>", self._on_search_key)
        self._search_job = None

        # Main split
        paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        # Left (tree)
        left = ttk.Frame(paned, width=360)
        paned.add(left, weight=1)

        self.tree = ttk.Treeview(left, columns=("fullpath",), show="tree", displaycolumns=())
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewOpen>>", self.on_open_node)
        self.tree.bind("<<TreeviewSelect>>", self.on_select_node)

        vsb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=vsb.set)

        # Tree right-click bindings (directory context)
        self.tree.bind("<Button-3>", self._tree_context_menu)
        self.tree.bind("<Button-2>", self._tree_context_menu)           # macOS alternative
        self.tree.bind("<Control-Button-1>", self._tree_context_menu)   # macOS ctrl+click

        # Right (preview)
        right = ttk.Frame(paned)
        paned.add(right, weight=3)

        if HtmlFrame is None:
            self.html = tk.Text(right, wrap="word")
            self.html.insert("1.0",
                "Install 'tkinterweb' for rich HTML preview:\n\n    pip install tkinterweb\n\n"
                "Currently using plain Text fallback."
            )
            self.html.config(state="disabled")
            self.html_is_webview = False
            self.status.set("Renderer: Text fallback")
        else:
            self.html = HtmlFrame(right, messages_enabled=False)
            self.html_is_webview = True
            self.status.set("Renderer: HtmlFrame")

        # Preview toolbar (copy/open)
        pv_tools = ttk.Frame(right)
        pv_tools.pack(fill=tk.X, side=tk.TOP, pady=(0, 4))
        ttk.Button(pv_tools, text="📋 Copy HTML", command=self._copy_html).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(pv_tools, text="📄 Copy Text", command=self._copy_text).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(pv_tools, text="↗ Open", command=self._open_external).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(pv_tools, text="copy+Img", command=self._copy_image_dataurl).pack(side=tk.LEFT)

        self.html.pack(fill=tk.BOTH, expand=True)

        # Bind copy/select and context menu on the preview widget
        self.html.bind_all("<Control-c>", self._on_preview_ctrl_c)
        # Right-click variants per platform:
        # - X11/Windows: <Button-3>
        # - macOS Aqua/Tk: <Button-2> is often right-click; Control-Click should also open menu
        self.html.bind("<Button-3>", self._show_preview_context_menu)
        self.html.bind("<Button-2>", self._show_preview_context_menu)
        self.html.bind("<Control-Button-1>", self._show_preview_context_menu)
        # Some widgets (e.g., HtmlFrame) may consume events; add global fallbacks
        self.bind_all("<Button-3>", self._preview_ctx_global, add="+")
        self.bind_all("<Button-2>", self._preview_ctx_global, add="+")
        self.bind_all("<Control-Button-1>", self._preview_ctx_global, add="+")
        # Bind Select All (Ctrl+A / Command+A) for preview pane
        self.html.bind_all("<Control-a>", self._on_preview_ctrl_a)
        self.html.bind_all("<Command-a>", self._on_preview_ctrl_a)

        # Status bar
        ttk.Label(self, textvariable=self.status, anchor="w").pack(fill=tk.X, side=tk.BOTTOM, padx=6, pady=4)


    def _choose_share_script(self):
        """Let the user choose a custom share.py (defaults to sibling share.py)."""
        path = filedialog.askopenfilename(title="Choose share.py",
                                          filetypes=[("Python script", "*.py"), ("All files", "*.*")])
        if not path:
            return
        self.share_script_path = path
        self.status.set(f"[Share] Script set: {os.path.basename(path)}")

    def _is_dir_shared(self, path: str) -> bool:
        info = self._shares.get(path)
        if not info:
            return False
        _, proc = info
        return proc.poll() is None

    def _update_dir_icon(self, dir_path: str):
        """Find tree item(s) for dir_path and update the displayed label depending on share state."""
        is_shared = self._is_dir_shared(dir_path)
        base = os.path.basename(dir_path) or dir_path
        label = f"{ICON_DIR_SHARED} {base}" if is_shared else base
        # Walk the tree to find nodes whose value == dir_path
        stack = list(self.tree.get_children(""))
        while stack:
            iid = stack.pop()
            stack.extend(self.tree.get_children(iid))
            vals = self.tree.item(iid, "values")
            if isinstance(vals, str):
                vals = (vals,) if vals else ()
            p = vals[0] if vals else ""
            if p == dir_path and os.path.isdir(p):
                if self.tree.item(iid, "text") != label:
                    self.tree.item(iid, text=label)
    def _open_share_in_browser(self, path: str):
        """Open the running share for this directory in the system default browser."""
        info = self._shares.get(path)
        if not info:
            self.status.set("[Share] Not running for this directory")
            return
        port, proc = info
        if proc.poll() is not None:
            self.status.set("[Share] Process is not running")
            return
        url = f"http://localhost:{port}/"
        try:
            webbrowser.open(url)
            self.status.set(f"[Share] Opened in browser: {url}")
        except Exception as e:
            self.status.set(f"[Share] Failed to open browser: {e}")
    # ---------- Preview utility actions ----------
    def _copy_html(self):
        """Copy the last rendered HTML to the clipboard (if available)."""
        data = getattr(self, "_last_html", None)
        if not data:
            self.status.set("[Copy] No HTML available")
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(data)
            self.status.set("[Copy] HTML copied")
        except Exception as e:
            self.status.set(f"[Copy] Failed: {e}")

    def _copy_text(self):
        """Copy the last plain text (source) to the clipboard (if available)."""
        data = getattr(self, "_last_plain", None)
        if data is None:
            self.status.set("[Copy] No text available")
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(data)
            self.status.set("[Copy] Text copied")
        except Exception as e:
            self.status.set(f"[Copy] Failed: {e}")

    def _open_external(self):
        """Open the currently selected file in the system default application."""
        sel = self.tree.selection()
        if not sel:
            self.status.set("[Open] No selection")
            return
        node_id = sel[0]
        vals = self.tree.item(node_id, "values")
        if isinstance(vals, str):
            vals = (vals,) if vals else ()
        path = vals[0] if vals else ""
        if not path or not os.path.isfile(path):
            self.status.set("[Open] Not a file")
            return
        try:
            if sys.platform.startswith("darwin"):
                os.system(f"open '{path}'")
            elif os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                os.system(f"xdg-open '{path}'")
            self.status.set("[Open] Opened externally")
        except Exception as e:
            self.status.set(f"[Open] Failed: {e}")

    def _copy_image_dataurl(self):
        """If current selection is an image file, copy as data URL to clipboard."""
        sel = self.tree.selection()
        if not sel:
            self.status.set("[Copy+Img] No selection")
            return
        node_id = sel[0]
        vals = self.tree.item(node_id, "values")
        if isinstance(vals, str):
            vals = (vals,) if vals else ()
        path = vals[0] if vals else ""
        if not path or not os.path.isfile(path):
            self.status.set("[Copy+Img] Not a file")
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in IMG_EXTS:
            self.status.set("[Copy+Img] Not an image file")
            return
        try:
            with open(path, "rb") as f:
                b = f.read()
            mime, _ = mimetypes.guess_type(path)
            if mime is None:
                mime = "image/png" if ext == ".png" else "image/jpeg"
            dataurl = "data:%s;base64,%s" % (mime, base64.b64encode(b).decode("ascii"))
            self.clipboard_clear()
            self.clipboard_append(dataurl)
            self.status.set("[Copy+Img] Data URL copied")
        except Exception as e:
            self.status.set(f"[Copy+Img] Failed: {e}")
    def _copy_image_bitmap(self):
        """Copy selected image file to the system clipboard as a real bitmap (best-effort).
        Windows: CF_DIB via ctypes (requires Pillow)
        macOS: NSPasteboard via PyObjC (if available), else fallback message
        Linux: xclip (if available), else fallback message
        """
        sel = self.tree.selection()
        if not sel:
            self.status.set("[Copy Bitmap] No selection")
            return
        node_id = sel[0]
        vals = self.tree.item(node_id, "values")
        if isinstance(vals, str):
            vals = (vals,) if vals else ()
        path = vals[0] if vals else ""
        if not path or not os.path.isfile(path):
            self.status.set("[Copy Bitmap] Not a file")
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in IMG_EXTS:
            self.status.set("[Copy Bitmap] Not an image file")
            return

        # Read image with Pillow
        try:
            from PIL import Image
        except Exception:
            self.status.set("[Copy Bitmap] Requires Pillow: pip install Pillow")
            return
        try:
            im = Image.open(path).convert("RGBA")
        except Exception as e:
            self.status.set(f"[Copy Bitmap] Open failed: {e}")
            return

        if sys.platform.startswith("win") or os.name == "nt":
            # Windows: put CF_DIB on clipboard
            try:
                import ctypes
                from ctypes import wintypes

                # Convert to DIB (BMP without file header)
                with io.BytesIO() as output:
                    # Save as BMP, then strip 14-byte BITMAPFILEHEADER
                    im2 = im.convert("RGB")  # CF_DIB typically expects BI_RGB without alpha
                    im2.save(output, format="BMP")
                    bmp_data = output.getvalue()
                dib_data = bmp_data[14:]

                CF_DIB = 8
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32
                OpenClipboard = user32.OpenClipboard
                EmptyClipboard = user32.EmptyClipboard
                SetClipboardData = user32.SetClipboardData
                CloseClipboard = user32.CloseClipboard
                GlobalAlloc = kernel32.GlobalAlloc
                GlobalLock = kernel32.GlobalLock
                GlobalUnlock = kernel32.GlobalUnlock
                GMEM_MOVEABLE = 0x0002

                if not OpenClipboard(None):
                    raise RuntimeError("OpenClipboard failed")
                try:
                    EmptyClipboard()
                    hGlobal = GlobalAlloc(GMEM_MOVEABLE, len(dib_data))
                    if not hGlobal:
                        raise MemoryError("GlobalAlloc failed")
                    pData = GlobalLock(hGlobal)
                    ctypes.memmove(pData, dib_data, len(dib_data))
                    GlobalUnlock(hGlobal)
                    if not SetClipboardData(CF_DIB, hGlobal):
                        # On failure, we must free hGlobal; but Windows owns it on success
                        raise RuntimeError("SetClipboardData failed")
                finally:
                    CloseClipboard()
                self.status.set("[Copy Bitmap] Copied to Windows clipboard")
                return
            except Exception as e:
                self.status.set(f"[Copy Bitmap] Windows failed: {e}")
                return

        if sys.platform.startswith("darwin"):
            # macOS: try PyObjC
            try:
                from AppKit import NSPasteboard, NSPasteboardTypePNG, NSImage
                from Foundation import NSData
                with io.BytesIO() as output:
                    im.save(output, format="PNG")
                    png_bytes = output.getvalue()
                pb = NSPasteboard.generalPasteboard()
                pb.clearContents()
                data = NSData.dataWithBytes_length_(png_bytes, len(png_bytes))
                img = NSImage.alloc().initWithData_(data)
                ok = pb.writeObjects_([img])
                if ok:
                    self.status.set("[Copy Bitmap] Copied to macOS clipboard")
                else:
                    self.status.set("[Copy Bitmap] macOS pasteboard write failed")
                return
            except Exception as e:
                self.status.set(f"[Copy Bitmap] macOS requires PyObjC: pip install pyobjc ({e})")
                return

        # Linux: try xclip PNG target
        try:
            with io.BytesIO() as output:
                im.save(output, format="PNG")
                png_bytes = output.getvalue()
            p = subprocess.Popen(["xclip", "-selection", "clipboard", "-t", "image/png", "-i"], stdin=subprocess.PIPE)
            p.communicate(png_bytes)
            if p.returncode == 0:
                self.status.set("[Copy Bitmap] Copied to X clipboard")
            else:
                self.status.set("[Copy Bitmap] xclip failed (install xclip)")
        except FileNotFoundError:
            self.status.set("[Copy Bitmap] Requires xclip on Linux: sudo apt install xclip")
        except Exception as e:
            self.status.set(f"[Copy Bitmap] Linux failed: {e}")

    def _get_text_selection(self) -> str | None:
        """Return selected text in Text fallback, or None if not applicable/empty."""
        if isinstance(self.html, tk.Text):
            try:
                return self.html.get("sel.first", "sel.last")
            except Exception:
                return None
        return None

    def _on_preview_ctrl_c(self, event=None):
        """Ctrl+C on preview: copy selection if possible; otherwise copy plain text fallback."""
        sel = self._get_text_selection()
        if sel:
            try:
                self.clipboard_clear()
                self.clipboard_append(sel)
                self.status.set("[Copy] Selection copied")
            except Exception as e:
                self.status.set(f"[Copy] Failed: {e}")
        else:
            # HtmlFrame selection is not exposed; fall back to last plain text
            data = getattr(self, "_last_plain", None)
            if data is None:
                self.status.set("[Copy] Nothing to copy")
            else:
                try:
                    self.clipboard_clear()
                    self.clipboard_append(data)
                    self.status.set("[Copy] Text copied")
                except Exception as e:
                    self.status.set(f"[Copy] Failed: {e}")
        return "break"

    def _on_preview_ctrl_a(self, event=None):
        """Select all in preview. Works for Text fallback; HtmlFrame is best-effort/no-op."""
        if isinstance(self.html, tk.Text):
            try:
                self.html.tag_add("sel", "1.0", "end-1c")
                self.html.focus_set()
                self.status.set("[Select All] Text selection set")
            except Exception as e:
                self.status.set(f"[Select All] Failed: {e}")
        else:
            # HtmlFrame does not expose a universal select-all API
            self.status.set("[Select All] Not supported in HTML viewer")
        return "break"

    def _show_preview_context_menu(self, event):
        """Right-click menu on preview: Copy, Copy as PNG (data URL), Copy as HTML/Markdown/TXT."""
        menu = tk.Menu(self, tearoff=0)

        def copy_selection_or_text():
            sel = self._get_text_selection()
            if sel:
                self.clipboard_clear(); self.clipboard_append(sel)
                self.status.set("[Copy] Selection copied")
            else:
                data = getattr(self, "_last_plain", None)
                if data is None:
                    self.status.set("[Copy] Nothing to copy")
                else:
                    self.clipboard_clear(); self.clipboard_append(data)
                    self.status.set("[Copy] Text copied")

        def copy_as_png():
            self._copy_image_dataurl()

        def copy_as_html():
            data = getattr(self, "_last_html", None)
            if not data:
                self.status.set("[Copy] No HTML available")
                return
            self.clipboard_clear(); self.clipboard_append(data)
            self.status.set("[Copy] HTML copied")

        def copy_as_markdown():
            # Best-effort: use plain text as markdown source
            data = getattr(self, "_last_plain", None)
            if data is None:
                self.status.set("[Copy] No Markdown available")
                return
            self.clipboard_clear(); self.clipboard_append(data)
            self.status.set("[Copy] Markdown copied")

        def copy_as_txt():
            data = getattr(self, "_last_plain", None)
            if data is None:
                self.status.set("[Copy] No Text available")
                return
            self.clipboard_clear(); self.clipboard_append(data)
            self.status.set("[Copy] Text copied")

        def select_all():
            self._on_preview_ctrl_a()

        menu.add_command(label="Select All", command=select_all)
        menu.add_separator()
        menu.add_command(label="Copy", command=copy_selection_or_text)
        menu.add_command(label="Copy as PNG", command=copy_as_png)
        menu.add_command(label="Copy as Bitmap", command=self._copy_image_bitmap)
        menu.add_command(label="Copy as HTML", command=copy_as_html)
        menu.add_command(label="Copy as Markdown", command=copy_as_markdown)
        menu.add_command(label="Copy as TXT", command=copy_as_txt)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _preview_ctx_global(self, event):
        """Global fallback to open preview context menu when underlying widget swallows events.
        Only triggers if the event occurred inside the preview widget or its descendants."""
        # Ascend the widget hierarchy to see whether event.widget is within self.html
        w = event.widget
        inside = False
        while True:
            if w is self.html:
                inside = True
                break
            if not hasattr(w, "master") or w.master is None:
                break
            w = w.master
        if not inside:
            return
        # Reuse the same context menu function
        self._show_preview_context_menu(event)
        return "break"

    def _ext_allowed(self, ext: str) -> bool:
        """Return True if the file extension is allowed by per-type toggles.
        Non-viewable types are not governed by these toggles (handled elsewhere)."""
        # If toggles do not exist yet (early UI), allow all
        for name in ("ft_md", "ft_html", "ft_csv", "ft_txt", "ft_png", "ft_jpg"):
            if not hasattr(self, name):
                return True
        if ext in MD_EXTS:
            return bool(self.ft_md.get())
        if ext in HTML_EXTS:
            return bool(self.ft_html.get())
        if ext in CSV_EXTS:
            return bool(self.ft_csv.get())
        if ext in TXT_EXTS:
            return bool(self.ft_txt.get())
        if ext == ".png":
            return bool(self.ft_png.get())
        if ext in (".jpg", ".jpeg"):
            return bool(self.ft_jpg.get())
        # For non-viewable files, this function is not authoritative
        return True

    def refresh_current_dir(self):
        """Refresh the currently selected directory. If a file is selected, refresh its parent.
        If nothing is selected, refresh the root directory."""
        # Determine target node
        sel = self.tree.selection()
        node_id = sel[0] if sel else ""
        if not node_id:
            roots = self.tree.get_children("")
            if not roots:
                return
            node_id = roots[0]

        # If a file is selected, use its parent directory
        vals = self.tree.item(node_id, "values")
        if isinstance(vals, str):
            vals = (vals,) if vals else ()
        path = vals[0] if vals else ""
        if path and os.path.isfile(path):
            parent = self.tree.parent(node_id)
            if not parent:
                return
            node_id = parent

        # Now node_id should be a directory: clear its children and re-populate
        for cid in list(self.tree.get_children(node_id)):
            self.tree.delete(cid)
        self._insert_dummy_child(node_id)
        self._populate_directory(node_id)

    # ---------- Directory sharing (share.py) ----------
    def _share_on_dir(self, path: str):
        """Start share.py on the given directory after asking for a port."""
        if not os.path.isdir(path):
            self.status.set("[Share] Not a directory")
            return
        # If already sharing, inform user
        if path in self._shares and self._shares[path][1].poll() is None:
            port = self._shares[path][0]
            self.status.set(f"[Share] Already ON at http://localhost:{port}")
            return
        # Propose the next available port based on last used + 1
        start = (getattr(self, "last_share_port", 8000) or 8000) + 1
        try:
            proposed = find_next_free_port(start)
        except Exception:
            proposed = 8000
        port = simpledialog.askinteger(
            "Share On", "Port:", initialvalue=proposed,
            minvalue=1, maxvalue=65535, parent=self
        )
        if port is None:
            return
        # Validate chosen port is free before launching
        if not is_port_available(port):
            messagebox.showerror("Share On", f"Port {port} is already in use. Choose another.")
            return
        share_script = self.share_script_path
        if not (share_script and os.path.isfile(share_script)):
            messagebox.showerror("Share On", "share.py not found. Set it via the 'Share Script…' button.")
            return
        try:
            popen_kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
            if sys.platform.startswith("win") or os.name == "nt":
                popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            else:
                popen_kwargs["start_new_session"] = True  # new process group on POSIX
            proc = subprocess.Popen([sys.executable, share_script, path, "--port", str(port)], **popen_kwargs)
            self._shares[path] = (port, proc)
            self.last_share_port = int(port)
            self.status.set(f"[Share] ON -> http://localhost:{port}  (dir: {os.path.basename(path)})")
            self._update_dir_icon(path)
        except Exception as e:
            messagebox.showerror("Share On", f"Failed to start share.py:\n{e}")

    def _share_off_dir(self, path: str):
        """Stop share.py for the given directory if running."""
        info = self._shares.get(path)
        if not info:
            self.status.set("[Share] Not running for this directory")
            return
        port, proc = info
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except Exception:
                    proc.kill()
            self.status.set(f"[Share] OFF (was :{port})")
        except Exception as e:
            self.status.set(f"[Share] Stop failed: {e}")
        finally:
            self._shares.pop(path, None)
            self._update_dir_icon(path)

    def _tree_context_menu(self, event):
        """Right-click menu on the Tree for directory actions (Share On/Off/Open Browser)."""
        row = self.tree.identify_row(event.y)
        if not row:
            return
        self.tree.selection_set(row)
        vals = self.tree.item(row, "values")
        if isinstance(vals, str):
            vals = (vals,) if vals else ()
        path = vals[0] if vals else ""
        if not path:
            return
        menu = tk.Menu(self, tearoff=0)
        if os.path.isdir(path):
            # If shared and running, show Open Browser + Share Off; otherwise Share On…
            info = self._shares.get(path)
            if info and info[1].poll() is None:
                menu.add_command(label="Open Browser", command=lambda p=path: self._open_share_in_browser(p))
                menu.add_command(label="Share Off", command=lambda p=path: self._share_off_dir(p))
            else:
                menu.add_command(label="Share On…", command=lambda p=path: self._share_on_dir(p))
        else:
            # For files, no share menu for now
            return
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # ---------- Tree / loading ----------
    def choose_folder(self):
        d = filedialog.askdirectory(title="Choose a folder")
        if d:
            self.load_root(d)

    def load_root(self, root: str):
        """Reset the tree and set a fresh root with a single dummy child."""
        # Ensure UI (and Tree) is initialized
        if not hasattr(self, "tree") or not isinstance(self.tree, ttk.Treeview):
            try:
                self._build_ui()
            except Exception as e:
                messagebox.showerror("UI Error", f"Tree not available and UI rebuild failed:\n{e}")
                return
        self.root_dir = root
        try:
            self.tree.delete(*self.tree.get_children())
        except Exception:
            # If the Tree was freshly created, it may have no children yet
            pass
        root_id = self.tree.insert("", "end", text=os.path.basename(root) or root, open=True, values=(root,))
        self._insert_dummy_child(root_id)

    def _insert_dummy_child(self, node_id):
        """Insert one dummy child so the node shows a disclosure arrow."""
        for c in self.tree.get_children(node_id):
            if self.tree.item(c, "text") == "dummy":
                return
        self.tree.insert(node_id, "end", text="dummy", values=("__DUMMY__",))

    def on_open_node(self, _evt):
        """Populate a directory node once when expanded; no duplicate children."""
        node_id = self.tree.focus()
        if not node_id:
            return
        self._populate_directory(node_id)

    def _populate_directory(self, node_id: str):
        # If already populated with a real child (non-dummy), bail
        for cid in self.tree.get_children(node_id):
            txt = self.tree.item(cid, "text")
            vals = self.tree.item(cid, "values")
            if isinstance(vals, str):
                vals = (vals,) if vals else ()
            is_dummy = (txt == "dummy") or (vals and vals[0] == "__DUMMY__")
            if not is_dummy:
                return

        # Remove dummies
        for cid in list(self.tree.get_children(node_id)):
            txt = self.tree.item(cid, "text")
            vals = self.tree.item(cid, "values")
            if isinstance(vals, str):
                vals = (vals,) if vals else ()
            if (txt == "dummy") or (vals and vals[0] == "__DUMMY__"):
                self.tree.delete(cid)

        # Get directory path
        vals = self.tree.item(node_id, "values")
        if isinstance(vals, str):
            vals = (vals,) if vals else ()
        if not vals:
            return
        fullpath = vals[0]

        try:
            entries = sorted(os.listdir(fullpath), key=str.lower)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to list directory:\n{e}")
            return

        show_only = bool(self.show_only_viewable.get())

        for name in entries:
            p = os.path.join(fullpath, name)
            if os.path.isdir(p):
                dir_label = f"{ICON_DIR_SHARED} {name}" if self._is_dir_shared(p) else decorate_name(name, p, is_dir=True)
                child = self.tree.insert(
                    node_id, "end",
                    text=dir_label,
                    open=False,
                    values=(p,)
                )
                self._insert_dummy_child(child)
            else:
                ext = os.path.splitext(p.lower())[1]
                # Respect both Viewable toggle and per-extension toggles
                if show_only and not is_viewable_file(p):
                    continue
                if (ext in VIEWABLE_EXTS) and (not self._ext_allowed(ext)):
                    continue
                self.tree.insert(
                    node_id, "end",
                    text=decorate_name(name, p, is_dir=False),
                    values=(p,)
                )

    # ---------- Selection / preview ----------
    def on_select_node(self, _evt):
        sel = self.tree.selection()
        if not sel:
            return
        node_id = sel[0]
        vals = self.tree.item(node_id, "values")
        if isinstance(vals, str):
            vals = (vals,) if vals else ()
        if not vals or vals[0] in ("", "__DUMMY__"):
            return

        path = vals[0]
        if os.path.isfile(path):
            self.render_file(path)

    # ---------- Search ----------
    def _on_search_key(self, _evt):
        if self._search_job:
            self.after_cancel(self._search_job)
        self._search_job = self.after(250, self.apply_search)

    def apply_search(self):
        pattern_text = (self.search_var.get() or "").strip()
        if not self.root_dir:
            return
        # Compile regex (default: case-insensitive to mirror previous behavior)
        if pattern_text:
            try:
                pattern_re = re.compile(pattern_text, re.IGNORECASE)
                self.status.set(f"[Search] regex pattern OK")
            except re.error as e:
                self.status.set(f"[Search] invalid regex: {e}")
                return
        else:
            pattern_re = None

        self.tree.delete(*self.tree.get_children())

        root_id = self.tree.insert("", "end", text=os.path.basename(self.root_dir) or self.root_dir, open=True, values=(self.root_dir,))

        if pattern_re is None:
            self._insert_dummy_child(root_id)
            return

        show_only = bool(self.show_only_viewable.get())

        for dirpath, dirnames, filenames in os.walk(self.root_dir):
            candidates = []
            if show_only:
                # Only viewable files are considered; directories are matched but still shown
                for name in dirnames:
                    if pattern_re.search(name):
                        candidates.append(os.path.join(dirpath, name))
                for fname in filenames:
                    if pattern_re.search(fname):
                        p = os.path.join(dirpath, fname)
                        if is_viewable_file(p):
                            ext = os.path.splitext(p.lower())[1]
                            if (ext in VIEWABLE_EXTS) and (not self._ext_allowed(ext)):
                                continue
                            candidates.append(p)
            else:
                # Directories always allowed; files checked against per-extension toggles when viewable
                for name in dirnames:
                    if pattern_re.search(name):
                        candidates.append(os.path.join(dirpath, name))
                for fname in filenames:
                    if pattern_re.search(fname):
                        p = os.path.join(dirpath, fname)
                        if os.path.isdir(p):
                            candidates.append(p)
                        else:
                            ext = os.path.splitext(p.lower())[1]
                            if (ext in VIEWABLE_EXTS) and (not self._ext_allowed(ext)):
                                continue
                            candidates.append(p)

            for p in candidates:
                parent_id = root_id
                rel = os.path.relpath(p, self.root_dir)
                parts = [] if rel == "." else rel.split(os.sep)
                walk = self.root_dir
                for part in parts[:-1]:
                    walk = os.path.join(walk, part)
                    found = None
                    for c in self.tree.get_children(parent_id):
                        vals_c = self.tree.item(c, "values")
                        if isinstance(vals_c, str):
                            vals_c = (vals_c,) if vals_c else ()
                        if vals_c and vals_c[0] == walk:
                            found = c
                            break
                    if not found:
                        base_walk = os.path.basename(walk)
                        label_walk = f"{ICON_DIR_SHARED} {base_walk}" if self._is_dir_shared(walk) else base_walk
                        found = self.tree.insert(parent_id, "end", text=label_walk, open=True, values=(walk,))
                    parent_id = found

                base = os.path.basename(p)
                is_dir = os.path.isdir(p)
                if is_dir:
                    node_text = f"{ICON_DIR_SHARED} {base}" if self._is_dir_shared(p) else decorate_name(base, p, is_dir=True)
                else:
                    node_text = decorate_name(base, p, is_dir=False)
                self.tree.insert(
                    parent_id, "end",
                    text=node_text,
                    open=False,
                    values=(p,)
                )

    # ---------- In-place filter (preserve expand/scroll/selection) ----------
    def _apply_viewable_filter(self):
        if not hasattr(self, "tree"):
            return
        show_only = bool(self.show_only_viewable.get())

        stack = list(self.tree.get_children(""))
        while stack:
            iid = stack.pop()
            stack.extend(self.tree.get_children(iid))

            vals = self.tree.item(iid, "values")
            if isinstance(vals, str):
                vals = (vals,) if vals else ()
            path = vals[0] if vals else ""

            if not path or path == "__DUMMY__":
                continue

            if os.path.isdir(path):
                # Always show directories
                try:
                    self.tree.reattach(iid, self.tree.parent(iid), "end")
                except Exception:
                    pass
            else:
                viewable = is_viewable_file(path)
                ext = os.path.splitext(path.lower())[1]
                disallowed_by_toggle = (ext in VIEWABLE_EXTS) and (not self._ext_allowed(ext))
                hide = (show_only and not viewable) or disallowed_by_toggle
                try:
                    if hide:
                        self.tree.detach(iid)
                    else:
                        self.tree.reattach(iid, self.tree.parent(iid), "end")
                except Exception:
                    pass

        # Clear selection if it points to a detached item
        for sid in list(self.tree.selection()):
            parent = self.tree.parent(sid)
            if sid not in self.tree.get_children(parent):
                self.tree.selection_remove(sid)

    # ---------- Rendering ----------
    def render_file(self, path: str):
        ext = os.path.splitext(path)[1].lower()
        if ext not in VIEWABLE_EXTS:
            self._show_message(
                f"Preview not available: {os.path.basename(path)}\n\n"
                f"Supported: {', '.join(sorted(VIEWABLE_EXTS))}"
            )
            return

        def work():
            # Handle images without reading file as text
            if ext in IMG_EXTS:
                file_url = Path(os.path.abspath(path)).as_uri()
                self._last_html = f"<img src='{file_url}' alt='image'>"
                self._last_plain = path

                def _apply_img():
                    if HtmlFrame is not None and hasattr(self.html, "load_url"):
                        try:
                            self.html.load_url(file_url)
                            mode = "HtmlFrame(url)"
                        except Exception:
                            # Fallback to HTML wrapper
                            html_doc = f"<html><body style='margin:0;background:#111;display:flex;align-items:center;justify-content:center;min-height:100vh'><img src='{file_url}' style='max-width:100%;height:auto;display:block'></body></html>"
                            self._set_html(html_doc)
                            mode = "HtmlFrame(html)" if getattr(self, "html_is_webview", False) else "Text(fallback)"
                    else:
                        html_doc = f"<html><body style='margin:0;background:#111;display:flex;align-items:center;justify-content:center;min-height:100vh'><img src='{file_url}' style='max-width:100%;height:auto;display:block'></body></html>"
                        self._set_html(html_doc)
                        mode = "HtmlFrame" if getattr(self, "html_is_webview", False) else "Text(fallback)"
                    self.status.set(f"[Image] Renderer: {mode}")
                self.after(0, _apply_img)
                return

            try:
                with open(path, "r", encoding="utf-8", newline="") as f:
                    text = f.read()
            except Exception as e:
                self._show_message(f"Open error: {e}")
                return

            if ext in HTML_EXTS:
                # Pass-through HTML; wrap if fragment; use base_url so relative assets resolve
                html_body = text
                body = html_body.strip().lower()
                if ("<html" not in body) or ("</html>" not in body):
                    html_body = f"<html><head><meta charset='utf-8'></head><body>{html_body}</body></html>"
                base_url = os.path.dirname(os.path.abspath(path))
                self._last_html = html_body
                self._last_plain = text

                def _apply_html():
                    if HtmlFrame is None:
                        self._show_message(html_body)
                        mode = "Text(fallback)"
                    else:
                        htmlframe_set(self.html, html_body, base_url=base_url)
                        mode = "HtmlFrame"
                    self.status.set(f"[HTML] Renderer: {mode}")
                self.after(0, _apply_html)
                return

            if ext in MD_EXTS:
                html_body, engine = render_markdown_to_html(text)
                html_doc = f"""
                <html><head><meta charset="utf-8"/>
                <style>
                  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Ubuntu, 'Helvetica Neue', Arial, sans-serif; padding: 16px; line-height: 1.5; }}
                  pre, code {{ background: #f6f8fa; }}
                  pre {{ padding: 12px; overflow: auto; border-radius: 6px; }}
                  h1,h2,h3,h4 {{ margin-top: 1.2em; }}
                  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
                  thead th {{ background: #fafafa; }}
                  th, td {{ border: 1px solid #ddd; padding: 6px 8px; vertical-align: top; }}
                </style></head><body>{html_body}</body></html>
                """
                self._last_html = html_doc
                self._last_plain = text
                def _apply_md():
                    self._set_html(html_doc)
                    mode = "HtmlFrame" if getattr(self, "html_is_webview", False) else "Text(fallback)"
                    self.status.set(f"[Markdown] Engine: {engine} | Renderer: {mode}")
                self.after(0, _apply_md)
                return

            if ext in CSV_EXTS:
                # Render CSV as an HTML table (safety caps)
                MAX_ROWS = 2000
                MAX_COLS = 200
                rows, truncated = [], False
                try:
                    with open(path, "r", encoding="utf-8", newline="") as f:
                        rdr = csv.reader(f)
                        for ri, row in enumerate(rdr):
                            if ri >= MAX_ROWS:
                                truncated = True
                                break
                            rows.append(row[:MAX_COLS])
                except Exception as e:
                    self._show_message(f"CSV read error: {e}")
                    return

                from html import escape as esc
                if rows:
                    header = rows[0]
                    thead = "<thead><tr>" + "".join(f"<th>{esc(h or '')}</th>" for h in header) + "</tr></thead>"
                    body_rows = rows[1:]
                else:
                    thead = ""
                    body_rows = []

                tbody = "<tbody>" + "".join(
                    "<tr>" + "".join(f"<td>{esc(cell or '')}</td>" for cell in r) + "</tr>"
                    for r in body_rows
                ) + "</tbody>"

                note = "<p style='font-size:12px;color:#666;margin:8px 0 0;'>CSV preview"
                if truncated:
                    note += f" (showing first {MAX_ROWS} rows, first {MAX_COLS} cols)</p>"
                else:
                    note += ".</p>"

                html_doc = f"""
                <html><head><meta charset="utf-8"/>
                <style>
                  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Ubuntu, 'Helvetica Neue', Arial, sans-serif; padding: 16px; line-height: 1.5; }}
                  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
                  th, td {{ border: 1px solid #ddd; padding: 6px 8px; vertical-align: top; }}
                  thead th {{ background: #fafafa; position: sticky; top: 0; }}
                  .wrap {{ overflow: auto; max-height: 72vh; }}
                </style></head>
                <body>
                  {note}
                  <div class="wrap">
                    <table>
                      {thead}
                      {tbody}
                    </table>
                  </div>
                </body></html>
                """
                self._last_html = html_doc
                self._last_plain = text
                def _apply_csv():
                    self._set_html(html_doc)
                    mode = "HtmlFrame" if getattr(self, "html_is_webview", False) else "Text(fallback)"
                    self.status.set(f"[CSV] Renderer: {mode}")
                self.after(0, _apply_csv)
                return

            if ext in TXT_EXTS:
                from html import escape as esc
                html_doc = f"""
                <html><head><meta charset="utf-8"/>
                <style>
                  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Ubuntu, 'Helvetica Neue', Arial, sans-serif; padding: 16px; line-height: 1.5; }}
                  pre {{ padding: 12px; overflow: auto; background:#f6f8fa; border-radius: 6px; }}
                </style></head><body>
                  <pre>{esc(text)}</pre>
                </body></html>
                """
                self._last_html = html_doc
                self._last_plain = text
                def _apply_txt():
                    self._set_html(html_doc)
                    mode = "HtmlFrame" if getattr(self, "html_is_webview", False) else "Text(fallback)"
                    self.status.set(f"[TXT] Renderer: {mode}")
                self.after(0, _apply_txt)
                return

        threading.Thread(target=work, daemon=True).start()

    # ---------- HTML/text helpers ----------
    def _show_message(self, text: str):
        self._last_html = None
        self._last_plain = text
        if HtmlFrame is None:
            self.html.config(state="normal")
            self.html.delete("1.0", tk.END)
            self.html.insert("1.0", text)
            self.html.config(state="disabled")
            self._ensure_text_readonly()
        else:
            safe = (
                "<html><head><meta charset='utf-8'></head>"
                "<body style='font-family:sans-serif;white-space:pre-wrap;padding:16px;'>"
                f"{self._escape_html(text)}</body></html>"
            )
            htmlframe_set(self.html, safe)
            # If we are in Text fallback, ensure selection/copy works
            self._ensure_text_readonly()

    def _set_html(self, html: str):
        if HtmlFrame is None:
            self._show_message(html)
        else:
            htmlframe_set(self.html, html)
            # If we are in Text fallback, ensure selection/copy works
            self._ensure_text_readonly()

    def _ensure_text_readonly(self):
        """Allow selection/copy in Text widget while blocking edits."""
        if isinstance(self.html, tk.Text):
            self.html.config(state="normal")
            # Block any key that would insert/delete text
            def _block_keys(evt):
                # Allow Ctrl+C / Ctrl+A / navigation keys
                if (evt.state & 0x4) and evt.keysym.lower() in ("c", "a"):
                    return None
                if evt.keysym in ("Left","Right","Up","Down","Home","End","Prior","Next"):
                    return None
                return "break"
            self.html.bind("<Key>", _block_keys)

    @staticmethod
    def _escape_html(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------- CLI ----------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Tree + Preview (MD/HTML/CSV/TXT)")
    parser.add_argument("path", nargs="?", default=None,
                        help="(Optional) start folder positional argument")
    parser.add_argument("-d", "--start-dir", dest="start_dir", default=None,
                        help="Start folder to load")
    parser.add_argument("-s", "--search", dest="initial_search", default=None,
                        help="Initial search term applied on startup")
    parser.add_argument("--view-alltype", action="store_true", dest="view_alltype",
                        help="Start with ALL types visible (disables 'Viewable only')")
    parser.add_argument("--kill-on-terminate", choices=["true","false","ask"], default="ask",
                        help="What to do with share servers on exit: true=always stop, false=keep running, ask=prompt (default)")
    args = parser.parse_args()

    start_dir = args.start_dir or args.path
    if start_dir:
        start_dir = os.path.abspath(os.path.expanduser(start_dir))
        if not os.path.isdir(start_dir):
            print(f"Warning: '{start_dir}' is not a directory. Falling back to current working directory.",
                  file=sys.stderr)
            start_dir = None

    app = App(start_dir=start_dir,
              initial_search=args.initial_search,
              visible_only=(not args.view_alltype),
              kill_on_terminate=args.kill_on_terminate)
    app.mainloop()