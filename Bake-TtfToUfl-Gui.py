#!/usr/bin/env python3
"""B1 GUI: bake UFL from TTF, or concatenate section bins in list order.

Scheme A bake: EN = fixed ASCII; FR = cmap-full sparse by default.
Merge tab: pick any section files (no name rules); order = concat order.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

ROOT = Path(__file__).resolve().parent
BAKE_PY = ROOT / "Bake-TtfToUfl.py"
DEFAULT_FA = ROOT / "Yekan_custom.ttf"
if not DEFAULT_FA.is_file():
    DEFAULT_FA = ROOT / "Yekan_New.ttf"
DEFAULT_EN = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "arial.ttf"
DEFAULT_OUT = ROOT / "out" / "ttf_spike_font_lib.bin"
DEFAULT_MERGE_OUT = ROOT / "out" / "font_lib_merged.bin"
DEFAULT_RANGES_HINT = (
    "# One range per line (FR only). Examples:\n"
    "# 0600-06FF\n"
    "# 0xFB50-0xFEFC\n"
    "# U+0020-U+007E\n"
)


class BakeGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("TTF → UFL (B1 bake / merge)")
        self.geometry("720x660")
        self.minsize(580, 540)

        self.var_en = tk.StringVar(value=str(DEFAULT_EN if DEFAULT_EN.is_file() else ""))
        self.var_fa = tk.StringVar(value=str(DEFAULT_FA if DEFAULT_FA.is_file() else ""))
        self.var_fa_b = tk.StringVar(value="")
        self.var_out = tk.StringVar(value=str(DEFAULT_OUT))
        self.var_merge_out = tk.StringVar(value=str(DEFAULT_MERGE_OUT))
        self.var_thr = tk.IntVar(value=128)
        self.var_custom = tk.BooleanVar(value=False)
        self._busy = False
        self._merge_paths: list[str] = []

        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        bake_frm = ttk.Frame(nb, padding=10)
        merge_frm = ttk.Frame(nb, padding=10)
        nb.add(bake_frm, text="Bake from TTF")
        nb.add(merge_frm, text="Merge sections")

        self._build_bake_tab(bake_frm)
        self._build_merge_tab(merge_frm)

    def _build_bake_tab(self, frm: ttk.Frame) -> None:
        self._row_file(frm, 0, "EN font (Western)", self.var_en, self._browse_en)
        self._row_file(frm, 1, "FA font A (e.g. Yekan)", self.var_fa, self._browse_fa)
        self._row_file(frm, 2, "FA font B (optional)", self.var_fa_b, self._browse_fa_b)
        self._row_file(frm, 3, "Output UFL .bin", self.var_out, self._browse_out)

        thr_row = ttk.Frame(frm)
        thr_row.grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 4))
        ttk.Label(thr_row, text="Gray threshold (0–255):").pack(side=tk.LEFT)
        ttk.Spinbox(thr_row, from_=1, to=255, textvariable=self.var_thr, width=6).pack(
            side=tk.LEFT, padx=6
        )

        opt = ttk.LabelFrame(frm, text="FR Unicode coverage (scheme A)", padding=8)
        opt.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=(4, 4))
        ttk.Label(
            opt,
            text="Default: cmap-full sparse. EN always ASCII U+0020..U+007E.",
        ).pack(anchor="w")
        ttk.Checkbutton(
            opt,
            text="Custom Unicode ranges (FR only)",
            variable=self.var_custom,
            command=self._toggle_ranges,
        ).pack(anchor="w", pady=(6, 2))
        self.txt_ranges = tk.Text(opt, height=5, wrap=tk.WORD)
        self.txt_ranges.pack(fill=tk.BOTH, expand=True)
        self.txt_ranges.insert("1.0", DEFAULT_RANGES_HINT)
        self.txt_ranges.configure(state=tk.DISABLED)

        btn_row = ttk.Frame(frm)
        btn_row.grid(row=6, column=0, columnspan=3, sticky="ew", pady=8)
        self.btn_bake = ttk.Button(btn_row, text="Bake UFL", command=self._on_bake)
        self.btn_bake.pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Open out folder", command=self._open_out).pack(
            side=tk.LEFT, padx=8
        )

        ttk.Label(frm, text="Log").grid(row=7, column=0, sticky="w")
        self.log = tk.Text(frm, height=10, wrap=tk.WORD)
        self.log.grid(row=8, column=0, columnspan=3, sticky="nsew")
        scroll = ttk.Scrollbar(frm, command=self.log.yview)
        scroll.grid(row=8, column=3, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)

        frm.columnconfigure(1, weight=1)
        frm.rowconfigure(5, weight=1)
        frm.rowconfigure(8, weight=2)

        self._append(
            "B1: PC bake only. Device uses the .bin via Download Probe Font / Font Lib.\n"
            "FR default = cmap-full sparse; EN = ASCII (scheme A).\n"
            "Optional FA B → dual family. Or use Merge sections tab for manual concat.\n"
            f"Bake script: {BAKE_PY}\n"
        )

    def _build_merge_tab(self, frm: ttk.Frame) -> None:
        ttk.Label(
            frm,
            text="Add section files in device order. Filenames are free; list order is concat order.\n"
            "Typical: 6 blocks (single family) or 9 (dual: …|FR20 + FR*_B).",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        list_frm = ttk.Frame(frm)
        list_frm.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self.merge_list = tk.Listbox(list_frm, selectmode=tk.EXTENDED, height=14)
        self.merge_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        mscroll = ttk.Scrollbar(list_frm, command=self.merge_list.yview)
        mscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.merge_list.configure(yscrollcommand=mscroll.set)

        side = ttk.Frame(frm)
        side.grid(row=1, column=1, sticky="ns")
        ttk.Button(side, text="Add…", command=self._merge_add).pack(fill=tk.X, pady=2)
        ttk.Button(side, text="Remove", command=self._merge_remove).pack(fill=tk.X, pady=2)
        ttk.Button(side, text="Move up", command=self._merge_up).pack(fill=tk.X, pady=2)
        ttk.Button(side, text="Move down", command=self._merge_down).pack(fill=tk.X, pady=2)
        ttk.Button(side, text="Clear", command=self._merge_clear).pack(fill=tk.X, pady=2)

        out_row = ttk.Frame(frm)
        out_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 4))
        ttk.Label(out_row, text="Output .bin").pack(side=tk.LEFT)
        ttk.Entry(out_row, textvariable=self.var_merge_out).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=6
        )
        ttk.Button(out_row, text="Browse…", command=self._browse_merge_out).pack(side=tk.LEFT)

        btn_row = ttk.Frame(frm)
        btn_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=8)
        self.btn_merge = ttk.Button(btn_row, text="Merge sections", command=self._on_merge)
        self.btn_merge.pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Open out folder", command=self._open_merge_out).pack(
            side=tk.LEFT, padx=8
        )

        ttk.Label(frm, text="Merge log").grid(row=4, column=0, sticky="w")
        self.merge_log = tk.Text(frm, height=8, wrap=tk.WORD)
        self.merge_log.grid(row=5, column=0, columnspan=2, sticky="nsew")
        mlog_scroll = ttk.Scrollbar(frm, command=self.merge_log.yview)
        mlog_scroll.grid(row=5, column=2, sticky="ns")
        self.merge_log.configure(yscrollcommand=mlog_scroll.set)

        frm.columnconfigure(0, weight=1)
        frm.rowconfigure(1, weight=2)
        frm.rowconfigure(5, weight=1)

    def _toggle_ranges(self) -> None:
        if self.var_custom.get():
            self.txt_ranges.configure(state=tk.NORMAL)
        else:
            self.txt_ranges.configure(state=tk.DISABLED)

    def _row_file(self, parent, row, label, var, browse_cmd) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", padx=6, pady=2)
        ttk.Button(parent, text="Browse…", command=browse_cmd).grid(row=row, column=2, pady=2)

    def _browse_en(self) -> None:
        p = filedialog.askopenfilename(
            title="EN TTF",
            filetypes=[("TrueType / OpenType", "*.ttf *.otf"), ("All", "*.*")],
            initialdir=str(Path(self.var_en.get()).parent) if self.var_en.get() else None,
        )
        if p:
            self.var_en.set(p)

    def _browse_fa(self) -> None:
        p = filedialog.askopenfilename(
            title="FA TTF (family A)",
            filetypes=[("TrueType / OpenType", "*.ttf *.otf"), ("All", "*.*")],
            initialdir=str(ROOT),
        )
        if p:
            self.var_fa.set(p)

    def _browse_fa_b(self) -> None:
        p = filedialog.askopenfilename(
            title="FA TTF (family B, optional)",
            filetypes=[("TrueType / OpenType", "*.ttf *.otf"), ("All", "*.*")],
            initialdir=str(ROOT),
        )
        if p:
            self.var_fa_b.set(p)

    def _browse_out(self) -> None:
        p = filedialog.asksaveasfilename(
            title="Output UFL bin",
            defaultextension=".bin",
            filetypes=[("UFL bin", "*.bin"), ("All", "*.*")],
            initialfile="ttf_spike_font_lib.bin",
            initialdir=str(ROOT / "out"),
        )
        if p:
            self.var_out.set(p)

    def _browse_merge_out(self) -> None:
        p = filedialog.asksaveasfilename(
            title="Merged UFL bin",
            defaultextension=".bin",
            filetypes=[("UFL bin", "*.bin"), ("All", "*.*")],
            initialfile="font_lib_merged.bin",
            initialdir=str(ROOT / "out"),
        )
        if p:
            self.var_merge_out.set(p)

    def _append(self, text: str) -> None:
        self.log.insert(tk.END, text)
        self.log.see(tk.END)

    def _merge_append(self, text: str) -> None:
        self.merge_log.insert(tk.END, text)
        self.merge_log.see(tk.END)

    def _refresh_merge_list(self) -> None:
        self.merge_list.delete(0, tk.END)
        for p in self._merge_paths:
            self.merge_list.insert(tk.END, p)

    def _merge_add(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Add section files (order preserved as selected)",
            filetypes=[("Binary / any", "*.bin *.*"), ("All", "*.*")],
            initialdir=str(ROOT / "out"),
        )
        if not paths:
            return
        for p in paths:
            self._merge_paths.append(p)
        self._refresh_merge_list()

    def _merge_remove(self) -> None:
        sel = list(self.merge_list.curselection())
        if not sel:
            return
        for i in reversed(sel):
            del self._merge_paths[i]
        self._refresh_merge_list()

    def _merge_up(self) -> None:
        sel = list(self.merge_list.curselection())
        if not sel or sel[0] == 0:
            return
        for i in sel:
            self._merge_paths[i - 1], self._merge_paths[i] = (
                self._merge_paths[i],
                self._merge_paths[i - 1],
            )
        self._refresh_merge_list()
        self.merge_list.selection_clear(0, tk.END)
        for i in sel:
            self.merge_list.selection_set(i - 1)

    def _merge_down(self) -> None:
        sel = list(self.merge_list.curselection())
        if not sel or sel[-1] >= len(self._merge_paths) - 1:
            return
        for i in reversed(sel):
            self._merge_paths[i + 1], self._merge_paths[i] = (
                self._merge_paths[i],
                self._merge_paths[i + 1],
            )
        self._refresh_merge_list()
        self.merge_list.selection_clear(0, tk.END)
        for i in sel:
            self.merge_list.selection_set(i + 1)

    def _merge_clear(self) -> None:
        self._merge_paths.clear()
        self._refresh_merge_list()

    def _open_out(self) -> None:
        out = Path(self.var_out.get())
        folder = out.parent if out.suffix else out
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(str(folder))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(folder)])

    def _open_merge_out(self) -> None:
        out = Path(self.var_merge_out.get())
        folder = out.parent if out.suffix else out
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(str(folder))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(folder)])

    def _on_merge(self) -> None:
        if self._busy:
            return
        if not self._merge_paths:
            messagebox.showerror("Error", "Add at least one section file.")
            return
        out = Path(self.var_merge_out.get().strip())
        if not out.name:
            messagebox.showerror("Error", "Set output path.")
            return
        for p in self._merge_paths:
            if not Path(p).is_file():
                messagebox.showerror("Error", f"Missing file:\n{p}")
                return
        if not BAKE_PY.is_file():
            messagebox.showerror("Error", f"Missing {BAKE_PY}")
            return

        out.parent.mkdir(parents=True, exist_ok=True)
        self._busy = True
        self.btn_merge.configure(state=tk.DISABLED)
        self._merge_append(f"\n--- Merge start ({len(self._merge_paths)} files) ---\n")
        for i, p in enumerate(self._merge_paths, 1):
            self._merge_append(f"  [{i}] {p}\n")
        self._merge_append(f"OUT={out}\n")

        paths = list(self._merge_paths)

        def worker() -> None:
            cmd = [
                sys.executable,
                "-u",
                str(BAKE_PY),
                "--merge",
                *paths,
                "--out",
                str(out),
            ]
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(ROOT),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                assert proc.stdout is not None
                for line in proc.stdout:
                    self.after(0, self._merge_append, line)
                rc = proc.wait()
            except Exception as exc:  # noqa: BLE001
                self.after(0, self._merge_done, -1, str(exc))
                return
            self.after(0, self._merge_done, rc, None)

        threading.Thread(target=worker, daemon=True).start()

    def _merge_done(self, rc: int, err: str | None) -> None:
        self._busy = False
        self.btn_merge.configure(state=tk.NORMAL)
        if err:
            self._merge_append(f"ERROR: {err}\n")
            messagebox.showerror("Merge failed", err)
            return
        if rc != 0:
            self._merge_append(f"Merge failed, exit={rc}\n")
            messagebox.showerror("Merge failed", f"Exit code {rc}")
            return
        out = Path(self.var_merge_out.get().strip())
        prod = out.parent / "font_lib_from_ttf.bin"
        try:
            if out.is_file():
                prod.write_bytes(out.read_bytes())
                self._merge_append(f"Also wrote {prod}\n")
        except OSError as exc:
            self._merge_append(f"Copy warning: {exc}\n")
        size = out.stat().st_size if out.is_file() else 0
        self._merge_append(f"--- Merge OK ({size} bytes) ---\n")
        messagebox.showinfo(
            "Merge OK",
            f"Wrote:\n{out}\n({size} bytes)\n\n"
            f"Also:\n{prod}\n\n"
            "Download Probe Font / Font Lib with this bin.",
        )

    def _on_bake(self) -> None:
        if self._busy:
            return
        en = Path(self.var_en.get().strip())
        fa = Path(self.var_fa.get().strip())
        fa_b_s = self.var_fa_b.get().strip()
        fa_b = Path(fa_b_s) if fa_b_s else None
        out = Path(self.var_out.get().strip())
        if not BAKE_PY.is_file():
            messagebox.showerror("Error", f"Missing {BAKE_PY}")
            return
        if not en.is_file():
            messagebox.showerror("Error", f"EN font not found:\n{en}")
            return
        if not fa.is_file():
            messagebox.showerror("Error", f"FA font A not found:\n{fa}")
            return
        if fa_b is not None and not fa_b.is_file():
            messagebox.showerror("Error", f"FA font B not found:\n{fa_b}")
            return
        try:
            thr = int(self.var_thr.get())
        except (tk.TclError, ValueError):
            messagebox.showerror("Error", "Threshold must be 1–255")
            return
        if thr < 1 or thr > 255:
            messagebox.showerror("Error", "Threshold must be 1–255")
            return

        fr_ranges_arg: str | None = None
        if self.var_custom.get():
            raw = self.txt_ranges.get("1.0", tk.END)
            lines = []
            for ln in raw.splitlines():
                s = ln.strip()
                if not s or s.startswith("#"):
                    continue
                lines.append(s)
            if not lines:
                messagebox.showerror(
                    "Error",
                    "Custom ranges enabled but empty.\n"
                    "Add ranges like 0600-06FF, or uncheck the option.",
                )
                return
            fr_ranges_arg = "\n".join(lines)

        out.parent.mkdir(parents=True, exist_ok=True)
        self._busy = True
        self.btn_bake.configure(state=tk.DISABLED)
        mode = "custom FR ranges" if fr_ranges_arg else "cmap-full sparse (default)"
        self._append(
            f"\n--- Bake start ---\nEN={en}\nFA_A={fa}\n"
            f"FA_B={fa_b if fa_b else '(none)'}\nOUT={out}\nthr={thr}\n"
            f"FR={mode}\n"
        )

        def worker() -> None:
            cmd = [
                sys.executable,
                "-u",
                str(BAKE_PY),
                "--en-font",
                str(en),
                "--font",
                str(fa),
                "--out",
                str(out),
                "--threshold",
                str(thr),
            ]
            if fa_b is not None:
                cmd.extend(["--font-b", str(fa_b)])
            if fr_ranges_arg:
                cmd.extend(["--fr-ranges", fr_ranges_arg])
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(ROOT),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                assert proc.stdout is not None
                for line in proc.stdout:
                    self.after(0, self._append, line)
                rc = proc.wait()
            except Exception as exc:  # noqa: BLE001
                self.after(0, self._bake_done, -1, str(exc))
                return
            self.after(0, self._bake_done, rc, None)

        threading.Thread(target=worker, daemon=True).start()

    def _bake_done(self, rc: int, err: str | None) -> None:
        self._busy = False
        self.btn_bake.configure(state=tk.NORMAL)
        if err:
            self._append(f"ERROR: {err}\n")
            messagebox.showerror("Bake failed", err)
            return
        if rc != 0:
            self._append(f"Bake failed, exit={rc}\n")
            messagebox.showerror("Bake failed", f"Exit code {rc}")
            return
        out = Path(self.var_out.get().strip())
        prod = out.parent / "font_lib_from_ttf.bin"
        try:
            if out.is_file():
                prod.write_bytes(out.read_bytes())
                self._append(f"Also wrote {prod}\n")
        except OSError as exc:
            self._append(f"Copy warning: {exc}\n")
        size = out.stat().st_size if out.is_file() else 0
        parts = out.parent / f"{out.stem}_parts"
        self._append(f"--- Bake OK ({size} bytes) ---\n")
        if parts.is_dir():
            self._append(f"Parts: {parts}\n")
        messagebox.showinfo(
            "Bake OK",
            f"Wrote:\n{out}\n({size} bytes)\n\n"
            f"Also per-block:\n{parts}\n"
            "(each *.bin + matching *_preview.png with ALL glyphs)\n\n"
            "Download Probe Font / Font Lib with the combined bin.",
        )


def main() -> int:
    if not BAKE_PY.is_file():
        print(f"Missing {BAKE_PY}", file=sys.stderr)
        return 1
    app = BakeGui()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
