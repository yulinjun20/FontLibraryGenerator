#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bake EN16|EN24|FR16|FR24|EN20|FR20 UFL for Font Probe.

Uses FreeType for raster + HarfBuzz for Arabic/Persian joining so presentation
slots (FB50..FEFC) match what device ConvertRule* looks up after shaping.

ConvertRule targets are always filled from HarfBuzz positional shaping (GSUB),
not from presentation-form cmap — required for fonts like IranSans that join
via OpenType rather than Unicode presentation forms.

Scheme A (default):
  EN = fixed ASCII U+0020..U+007E (dense contiguous block)
  FR = cmap-full sparse (only real glyphs; no empty placeholders)
  Custom Unicode ranges apply to FR only (--fr-ranges / GUI checkbox)

Dual family (optional --font-b):
  EN16|EN24|FR16_A|FR24_A|EN20|FR20_A|FR16_B|FR24_B|FR20_B
  Shared EN; device selects family A/B via Lib_FontSetFamily.

Device path stays FriBidi + ConvertRule* — this script only improves the bin.
"""
from __future__ import annotations

import argparse
import os
import struct
import sys
from pathlib import Path

import freetype
import uharfbuzz as hb
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
DEFAULT_FA_FONT = ROOT / "Yekan_New.ttf"
DEFAULT_EN_FONT = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "arial.ttf"
OUT_DEFAULT = ROOT / "out" / "ttf_spike_font_lib.bin"

# Device Arbic_Position[0x621..0x64A] indexed by POS_LAST/FIRST/MIDILE/ALONE
# (= last, first, middle, alone) — same order as lcd.c tables.
ARBIC_POSITION = [
    (0xFE80, 0xFE80, 0xFE80, 0xFE80),
    (0xFE82, 0xFE81, 0xFE82, 0xFE81),
    (0xFE84, 0xFE83, 0xFE84, 0xFE83),
    (0xFE86, 0xFE85, 0xFE86, 0xFE85),
    (0xFE88, 0xFE87, 0xFE88, 0xFE87),
    (0xFE8A, 0xFE8B, 0xFE8C, 0xFE89),
    (0xFE8E, 0xFE8D, 0xFE8E, 0xFE8D),
    (0xFE90, 0xFE91, 0xFE92, 0xFE8F),
    (0xFE94, 0xFE93, 0xFE94, 0xFE93),
    (0xFE96, 0xFE97, 0xFE98, 0xFE95),
    (0xFE9A, 0xFE9B, 0xFE9C, 0xFE99),
    (0xFE9E, 0xFE9F, 0xFEA0, 0xFE9D),
    (0xFEA2, 0xFEA3, 0xFEA4, 0xFEA1),
    (0xFEA6, 0xFEA7, 0xFEA8, 0xFEA5),
    (0xFEAA, 0xFEA9, 0xFEAA, 0xFEA9),
    (0xFEAC, 0xFEAB, 0xFEAC, 0xFEAB),
    (0xFEAE, 0xFEAD, 0xFEAE, 0xFEAD),
    (0xFEB0, 0xFEAF, 0xFEB0, 0xFEAF),
    (0xFEB2, 0xFEB3, 0xFEB4, 0xFEB1),
    (0xFEB6, 0xFEB7, 0xFEB8, 0xFEB5),
    (0xFEBA, 0xFEBB, 0xFEBC, 0xFEB9),
    (0xFEBE, 0xFEBF, 0xFEC0, 0xFEBD),
    (0xFEC2, 0xFEC3, 0xFEC4, 0xFEC1),
    (0xFEC6, 0xFEC7, 0xFEC8, 0xFEC5),
    (0xFECA, 0xFECB, 0xFECC, 0xFEC9),
    (0xFECE, 0xFECF, 0xFED0, 0xFECD),
    (0x063B, 0x063B, 0x063B, 0x063B),
    (0x063C, 0x063C, 0x063C, 0x063C),
    (0x063D, 0x063D, 0x063D, 0x063D),
    (0x063E, 0x063E, 0x063E, 0x063E),
    (0x063F, 0x063F, 0x063F, 0x063F),
    (0x0640, 0x0640, 0x0640, 0x0640),
    (0xFED2, 0xFED3, 0xFED4, 0xFED1),
    (0xFED6, 0xFED7, 0xFED8, 0xFED5),
    (0xFEDA, 0xFEDB, 0xFEDC, 0xFED9),
    (0xFEDE, 0xFEDF, 0xFEE0, 0xFEDD),
    (0xFEE2, 0xFEE3, 0xFEE4, 0xFEE1),
    (0xFEE6, 0xFEE7, 0xFEE8, 0xFEE5),
    (0xFEEA, 0xFEEB, 0xFEEC, 0xFEE9),
    (0xFEEE, 0xFEED, 0xFEEE, 0xFEED),
    (0xFEF0, 0xFEF3, 0xFEF4, 0xFEEF),
    (0xFEF2, 0xFEF3, 0xFEF4, 0xFEF1),
]

# Persian_AlphabetTab: last, first, middle, alone
PERSIAN_TAB = [
    (0x067E, (0xFB57, 0xFB58, 0xFB59, 0xFB56)),
    (0x0686, (0xFB7B, 0xFB7C, 0xFB7D, 0xFB7A)),
    (0x0698, (0xFB8B, 0xFB8A, 0xFB8B, 0xFB8A)),
    (0x06A9, (0xFB8F, 0xFB90, 0xFB91, 0xFB8E)),
    (0x06AF, (0xFB93, 0xFB94, 0xFB95, 0xFB92)),
    (0x06CC, (0xFBFD, 0xFBFE, 0xFBFF, 0xFBFC)),
]

# Contexts that typically yield isol / init / medi / fina for dual-joining letters.
# (prev, next) around the target letter.
POS_CONTEXT = {
    3: (None, None),          # alone / isol
    1: (None, 0x0645),        # first / init  (followed by meem)
    2: (0x0645, 0x0645),      # middle / medi
    0: (0x0645, None),        # last / fina   (preceded by meem)
}


def load_cmap(path: Path) -> dict[int, int]:
    """Map Unicode CP -> FreeType glyph index."""
    font = TTFont(str(path))
    best = font.getBestCmap() or {}
    out: dict[int, int] = {}
    for cp, name in best.items():
        try:
            out[int(cp)] = int(font.getGlyphID(name))
        except Exception:
            continue
    return out


def empty_glyph(px: int, advance: int = 1) -> bytes:
    """1x1 blank cell; dwidth keeps FreeType advance (critical for U+0020)."""
    bits = b"\x00"
    adv = max(1, min(100, advance if advance > 0 else 1))
    return bytes([1, 1, 0, 0, adv & 0xFF, 1, 0]) + bits


def _clamp_s8(v: int) -> int:
    if v > 127:
        return 127
    if v < -128:
        return -128
    return v


def _ink_density(ink: list[list[int]]) -> float:
    if not ink or not ink[0]:
        return 0.0
    total = sum(sum(row) for row in ink)
    return total / float(len(ink) * len(ink[0]))


def pack_glyph(
    bitmap_buffer,
    width: int,
    rows: int,
    pitch: int,
    advance_px: int,
    thr: int,
    bearing_x: int = 0,
    bearing_y: int = 0,
    join_tighten: bool = False,
    thin_fr: bool = False,
) -> bytes:
    """Convert FT gray bitmap to 1bpp MSB-first glyph blob.

    dwidth uses FreeType advance (allows joining overlap when adv < ink width).
    x/y_offset keep left/top bearing after ink crop.

    join_tighten (FR / joining scripts): dwidth ≤ ink_right + 1 so consecutive
    presentation forms match Old un_font join overlap (~16%). thin_fr reserved
    (unused: keep slack=+1). Not per-CP.
    """
    if width <= 0 or rows <= 0 or not bitmap_buffer:
        return empty_glyph(max(1, rows), advance_px)

    ink = []
    for y in range(rows):
        row = []
        for x in range(width):
            v = bitmap_buffer[y * pitch + x]
            row.append(1 if v >= thr else 0)
        ink.append(row)

    min_x, max_x, min_y, max_y = width, -1, rows, -1
    for y in range(rows):
        for x in range(width):
            if ink[y][x]:
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)
    if max_x < 0:
        return empty_glyph(max(1, rows), advance_px)

    cw = max_x - min_x + 1
    ch = max_y - min_y + 1
    cw = min(cw, 100)
    ch = min(ch, 48)
    out_pitch = (cw + 7) // 8
    bits = bytearray(out_pitch * ch)
    for y in range(ch):
        for x in range(cw):
            if ink[min_y + y][min_x + x]:
                bi = y * out_pitch + (x // 8)
                bits[bi] |= 1 << (7 - (x % 8))

    # Device LCD/print: startY += fontH - y_offset - height  (BDF-style).
    # y_offset = offset of bitmap BOTTOM from baseline (0 = sits on baseline;
    # negative = descender). FT bitmap_top is ink TOP → y = top - height.
    x_off = _clamp_s8(bearing_x + min_x)
    ink_top = bearing_y - min_y  # baseline → cropped ink top
    y_off = _clamp_s8(ink_top - ch)

    dwidth = max(1, advance_px if advance_px > 0 else (cw + 1))
    if join_tighten:
        # Next glyph originates at +dwidth; ink occupies [x_off, x_off+cw).
        ink_right = x_off + cw
        if ink_right > 0:
            # Align Old un_font: dwidth ≤ ink right edge + 1 (not extra overlap).
            slack = 1
            dwidth = min(dwidth, ink_right + slack)
        dwidth = max(1, dwidth)
    dwidth = min(100, dwidth)
    hdr = bytes([
        cw & 0xFF,
        ch & 0xFF,
        x_off & 0xFF,
        y_off & 0xFF,
        dwidth & 0xFF,
        len(bits) & 0xFF,
        (len(bits) >> 8) & 0xFF,
    ])
    return hdr + bytes(bits)


def _ft_bitmap_to_gray(bmp) -> tuple[bytes, int, int, int]:
    """Return (gray_buf, width, rows, pitch) for pack_glyph. Mono → 0/255."""
    w, rows, pitch = bmp.width, bmp.rows, bmp.pitch
    raw = bytes(bmp.buffer) if w and rows else b""
    if not raw:
        return b"", 0, 0, 0
    # FT_PIXEL_MODE_MONO == 1; GRAY == 2
    if getattr(bmp, "pixel_mode", 2) == 1:
        out = bytearray(w * rows)
        for y in range(rows):
            for x in range(w):
                byte = raw[y * pitch + (x >> 3)]
                if byte & (0x80 >> (x & 7)):
                    out[y * w + x] = 255
        return bytes(out), w, rows, w
    return raw, w, rows, pitch


class FontRaster:
    def __init__(self, path: Path, px: int, thr: int = 128, mono: bool = False):
        self.path = path
        self.px = px
        self.thr = thr  # FreeType gray is 0..255; keep ink if >= thr
        # mono=True: FT B/W + autohint — steadier stem weight for Latin at 16/20/24.
        self.mono = mono
        self.face = freetype.Face(str(path))
        self.face.set_pixel_sizes(0, px)
        self.cmap = load_cmap(path)

        blob = hb.Blob.from_file_path(str(path))
        self.hb_face = hb.Face(blob)
        self.hb_font = hb.Font(self.hb_face)
        self.hb_font.ptem = float(px)
        # Scale in 26.6; pixel size ≈ px
        self.hb_font.scale = (px * 64, px * 64)

    def render_gid(self, gid: int) -> bytes:
        if gid <= 0:
            return empty_glyph(self.px)
        # FORCE_AUTOHINT snaps stems to pixel grid (reduces thick/thin stems).
        # FORCE_AUTOHINT snaps stems to pixel grid (reduces thick/thin stems).
        flags = freetype.FT_LOAD_RENDER | freetype.FT_LOAD_FORCE_AUTOHINT
        if self.mono:
            flags |= freetype.FT_LOAD_TARGET_MONO
        else:
            flags |= freetype.FT_LOAD_TARGET_NORMAL
        self.face.load_glyph(gid, flags)
        glyph = self.face.glyph
        bmp = glyph.bitmap
        if self.mono:
            # Latin: round advance for even stems.
            adv = max(1, (glyph.advance.x + 32) >> 6)
        else:
            # FR: floor advance (Old un_font is tighter than rounded FT).
            adv = max(1, glyph.advance.x >> 6)
        buf, w, rows, pitch = _ft_bitmap_to_gray(bmp)
        if not w or not rows:
            return empty_glyph(self.px, adv)
        # Mono is already 0/255.
        # FR (all faces, aligned to proven Old-overlap bake):
        #   1) floor advance  2) dwidth ≤ ink_right+1  3) thr×3/4 keep AA joins.
        # No embolden/dilate — those filled counters / drifted from Old.
        if self.mono:
            thr = 1
            join_tighten = False
        else:
            thr = max(1, (self.thr * 3) // 4)
            join_tighten = True
        return pack_glyph(
            buf, w, rows, pitch, adv, thr,
            bearing_x=int(glyph.bitmap_left),
            bearing_y=int(glyph.bitmap_top),  # baseline→ink-top (device y_offset)
            join_tighten=join_tighten,
            thin_fr=False,
        )

    def render_cp(self, cp: int) -> bytes:
        # Missing cmap → real empty slot (do NOT load_char: that draws .notdef tofu).
        gid = self.cmap.get(cp, 0)
        if gid <= 0:
            return empty_glyph(self.px)
        return self.render_gid(gid)

    def shape_infos(self, text: str) -> list[tuple[int, int]]:
        """Return [(gid, cluster), ...] after shaping. cluster = logical char index."""
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.hb_font, buf)
        return [(int(i.codepoint), int(i.cluster)) for i in buf.glyph_infos]

    def shape_gids(self, text: str) -> list[int]:
        return [gid for gid, _cl in self.shape_infos(text)]

    def render_shaped_logical(self, text: str, logical_index: int) -> bytes:
        """
        Rasterize the glyph that HarfBuzz assigned to text[logical_index].

        Must use cluster IDs — not visual buffer indices. Arabic/Persian runs
        are RTL: visual[0] is often the last logical letter, so index-based
        picks write the wrong positional form into ConvertRule slots.
        """
        infos = self.shape_infos(text)
        if not infos:
            return empty_glyph(self.px)
        # Exact cluster match (normal for 1:1 letter → glyph).
        for gid, cl in infos:
            if cl == logical_index:
                return self.render_gid(gid)
        # Ligature / merged cluster: glyph owns a start cluster <= target.
        best: tuple[int, int] | None = None  # (cluster, gid)
        for gid, cl in infos:
            if cl <= logical_index and (best is None or cl > best[0]):
                best = (cl, gid)
        if best is not None:
            return self.render_gid(best[1])
        return self.render_gid(infos[0][0])


def build_presentation_sources(raster: FontRaster) -> dict[int, bytes]:
    """
    Fill presentation slots for device ConvertRule* lookups.

    Root contract (device): FriBidi + ConvertRule maps letters to FE*/FB*
    presentation codepoints, then GetFont indexes those CPs in the UFL.
    So every ConvertRule target slot must hold the *positional* glyph.

    Modern TTFs (IranSans and many others) join via OpenType GSUB and often
    lack a complete/correct presentation-form cmap. Therefore ConvertRule
    targets are authored from HarfBuzz positional shaping — that is the
    source of truth for all fonts.

    Glyph selection uses HB cluster IDs (logical char index), never visual
    buffer order — required for correct init/medi/fina under RTL.

    Remaining FB50..FEFC cmap entries (outside ConvertRule) are supplemental.
    """
    out: dict[int, bytes] = {}
    hb_n = 0
    cmap_extra_n = 0
    convert_rule_cps: set[int] = set()

    def put_ink(cp: int, blob: bytes, *, count_hb: bool = False) -> None:
        nonlocal hb_n, cmap_extra_n
        if not _blob_has_ink(blob) and cp != 0x0020:
            return
        if 0xFB50 <= cp <= 0xFEFC or (0x0600 <= cp <= 0x06FF):
            out[cp] = blob
            if count_hb:
                hb_n += 1
            else:
                cmap_extra_n += 1

    def hb_positional(logical: int, form_cp: int, pos: int) -> None:
        """Write ConvertRule slot from HB context; cluster-select the target letter."""
        nonlocal convert_rule_cps
        convert_rule_cps.add(form_cp)
        prev, nxt = POS_CONTEXT[pos]
        parts: list[str] = []
        if prev is not None:
            parts.append(chr(prev))
        parts.append(chr(logical))
        if nxt is not None:
            parts.append(chr(nxt))
        text = "".join(parts)
        logical_index = 0 if prev is None else 1
        blob = raster.render_shaped_logical(text, logical_index)
        if not _blob_has_ink(blob):
            if form_cp in raster.cmap:
                blob = raster.render_cp(form_cp)
            if not _blob_has_ink(blob):
                blob = raster.render_cp(logical)
        put_ink(form_cp, blob, count_hb=True)

    # 1) ConvertRule tables — HB is authoritative for every font.
    for i, forms in enumerate(ARBIC_POSITION):
        logical = 0x0621 + i
        for pos, form_cp in enumerate(forms):
            if 0x0600 <= form_cp <= 0x06FF:
                # Table holes that still point at logical Arabic (non-joining).
                convert_rule_cps.add(form_cp)
                put_ink(form_cp, raster.render_cp(form_cp), count_hb=False)
                continue
            hb_positional(logical, form_cp, pos)

    for logical, forms in PERSIAN_TAB:
        for pos, form_cp in enumerate(forms):
            hb_positional(logical, form_cp, pos)

    # Lam-Alef ligatures: one shaped glyph covers both logical letters (cluster 0).
    for form_cp, pair in (
        (0xFEF5, "\u0644\u0622"),
        (0xFEF6, "\u0644\u0622"),
        (0xFEF7, "\u0644\u0623"),
        (0xFEF8, "\u0644\u0623"),
        (0xFEF9, "\u0644\u0625"),
        (0xFEFA, "\u0644\u0625"),
        (0xFEFB, "\u0644\u0627"),
        (0xFEFC, "\u0644\u0627"),
    ):
        convert_rule_cps.add(form_cp)
        blob = raster.render_shaped_logical(pair, 0)
        if not _blob_has_ink(blob) and form_cp in raster.cmap:
            blob = raster.render_cp(form_cp)
        put_ink(form_cp, blob, count_hb=True)

    # 2) Supplemental presentation cmap (not in ConvertRule set).
    for cp in range(0xFB50, 0xFEFC + 1):
        if cp in convert_rule_cps or cp not in raster.cmap:
            continue
        put_ink(cp, raster.render_cp(cp), count_hb=False)

    print(
        f"  presentation fills: hb_convert_rule={hb_n} "
        f"cmap_extra={cmap_extra_n} total={len(out)}"
    )
    return out


def _blob_has_ink(blob: bytes) -> bool:
    if len(blob) < 7:
        return False
    w, h = blob[0], blob[1]
    nbytes = struct.unpack_from("<H", blob, 5)[0]
    return _glyph_ink_pixels(w, h, blob[7 : 7 + nbytes]) >= 4


def _cps_to_runs(cps: list[int]) -> list[tuple[int, int]]:
    if not cps:
        return []
    runs: list[tuple[int, int]] = []
    a = b = cps[0]
    for x in cps[1:]:
        if x == b + 1:
            b = x
        else:
            runs.append((a, b))
            a = b = x
    runs.append((a, b))
    return runs


def load_bdf_encodings(bdf_path: Path) -> list[int]:
    """Read ENCODING list from a guitool/BdfEditor .bdf (whitelist)."""
    encs: list[int] = []
    for ln in bdf_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ln.startswith("ENCODING"):
            encs.append(int(ln.split()[1]))
    return sorted(set(encs))


def _parse_cp_token(tok: str) -> int:
    """Parse one codepoint as hex: 0x0600 / U+0600 / bare 0600."""
    s = tok.strip().replace("U+", "").replace("u+", "").replace("_", "")
    if not s:
        raise ValueError(f"Empty codepoint token: {tok!r}")
    if s.lower().startswith("0x"):
        s = s[2:]
    return int(s, 16)


def parse_unicode_ranges(text: str) -> list[tuple[int, int]]:
    """
    Parse user ranges. One range per line or comma-separated.
    Forms: 0600-06FF  |  0x0600-0x06FF  |  U+0600..U+06FF
    """
    raw = text.replace(",", "\n").replace(";", "\n")
    out: list[tuple[int, int]] = []
    for ln in raw.splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        s = s.replace("U+", "").replace("u+", "").replace("..", "-")
        if "-" not in s:
            raise ValueError(f"Bad range (need start-end): {ln!r}")
        a, b = s.split("-", 1)
        lo = _parse_cp_token(a)
        hi = _parse_cp_token(b)
        if lo > hi:
            raise ValueError(f"Bad range start>end: {ln!r}")
        if lo < 0 or hi > 0x10FFFF:
            raise ValueError(f"Range out of Unicode: {ln!r}")
        out.append((lo, hi))
    if not out:
        raise ValueError("No Unicode ranges parsed")
    return out


def collect_cmap_all_cps(raster: FontRaster) -> list[int]:
    """All Unicode codepoints present in the TTF cmap (gid > 0)."""
    return sorted(cp for cp, gid in raster.cmap.items() if gid > 0)


def collect_cps_in_custom_ranges(
    raster: FontRaster,
    ranges: list[tuple[int, int]],
) -> list[int]:
    """Codepoints in custom ranges that exist in TTF cmap (no empty placeholders)."""
    cps: set[int] = set()
    for lo, hi in ranges:
        for cp in range(lo, hi + 1):
            if raster.cmap.get(cp, 0) > 0:
                cps.add(cp)
    return sorted(cps)


def collect_fr_sparse_cps(
    raster: FontRaster,
    ranges: list[tuple[int, int]] | None,
    pres: dict[int, bytes] | None,
) -> list[int]:
    """
    FR sparse set (scheme A): only real glyphs, no empty placeholders.
    ranges=None → full TTF cmap; else → intersection of custom ranges ∩ cmap.
    Always union ink presentation fills (HB gaps) that fall in scope.
    Always include ASCII '0'..'9' when FA has them or has U+06F0..06F9
    (UN637 GetFont remaps Persian digits → '0'..'9' in FR section).
    """
    if ranges is None:
        cps: set[int] = set(collect_cmap_all_cps(raster))
    else:
        cps = set(collect_cps_in_custom_ranges(raster, ranges))
    if pres:
        for cp, blob in pres.items():
            if not _blob_has_ink(blob):
                continue
            if ranges is None or any(lo <= cp <= hi for lo, hi in ranges):
                cps.add(cp)
    # Ensure FR has slots for remapped Persian digits (index '0'..'9').
    for i in range(10):
        ascii_d = 0x0030 + i
        persian_d = 0x06F0 + i
        if raster.cmap.get(ascii_d, 0) > 0 or raster.cmap.get(persian_d, 0) > 0:
            cps.add(ascii_d)
        if persian_d in cps or (pres and persian_d in pres):
            cps.add(ascii_d)
    # Family B uses FR for Western too — keep ASCII printable if FA cmap has them.
    for cp in range(0x0020, 0x007F):
        if raster.cmap.get(cp, 0) > 0:
            cps.add(cp)
    return sorted(cps)


def collect_guitool_like_cps(
    raster: FontRaster,
    pres: dict[int, bytes] | None,
    whitelist: list[int] | None = None,
) -> list[int]:
    """Legacy helper: whitelist or fixed guitool-ish ranges."""
    if whitelist is not None:
        return sorted(set(whitelist) | {0x0020})
    cps: set[int] = set()
    for lo, hi in ((0x0020, 0x007E), (0x00A0, 0x00FF), (0x0600, 0x06FF), (0xFB50, 0xFEFC)):
        for cp in range(lo, hi + 1):
            if raster.cmap.get(cp, 0) > 0:
                cps.add(cp)
    if pres:
        for cp, blob in pres.items():
            if 0xFB50 <= cp <= 0xFEFC and _blob_has_ink(blob):
                cps.add(cp)
    cps.add(0x0020)
    return sorted(cps)


def _pack_ufl_sections(sections: list[tuple[int, int, list[bytes]]], px: int) -> bytes:
    total = sum(len(g) for _f, _l, g in sections)
    n_sec = len(sections)
    head_size = 40
    sec_table = n_sec * 8
    index_off = head_size + sec_table
    index_bytes = total * 4
    data_off = index_off + index_bytes

    body = bytearray(data_off)
    offs: list[int] = []
    for _first, _last, glyphs in sections:
        for g in glyphs:
            offs.append(len(body))
            body.extend(g)

    file_size = len(body)
    body[0:4] = b"UFL\x81"
    struct.pack_into("<I", body, 4, file_size)
    struct.pack_into("<I", body, 8, head_size)
    body[12] = 0
    body[13] = n_sec & 0xFF
    struct.pack_into("<H", body, 14, 1)
    struct.pack_into("<i", body, 16, 1)
    body[20] = px & 0xFF
    body[21] = px & 0xFF
    struct.pack_into("<i", body, 24, px - 2)
    struct.pack_into("<i", body, 28, 2)
    struct.pack_into("<i", body, 32, total)
    struct.pack_into("<i", body, 36, total)

    gi = 0
    for s, (first, last, glyphs) in enumerate(sections):
        so = head_size + s * 8
        struct.pack_into("<H", body, so, first)
        struct.pack_into("<H", body, so + 2, last)
        sec_index = index_off + gi * 4
        struct.pack_into("<I", body, so + 4, sec_index)
        for j in range(len(glyphs)):
            struct.pack_into("<I", body, sec_index + j * 4, offs[gi + j])
        gi += len(glyphs)

    print(f"block px={px} nSec={n_sec} glyphs={total} size={file_size}")
    return bytes(body)


def build_block(raster: FontRaster, ranges: list[tuple[int, int]], pres: dict[int, bytes] | None) -> bytes:
    """Dense First..Last ranges (legacy); includes empty placeholders."""
    sections: list[tuple[int, int, list[bytes]]] = []
    for first, last in ranges:
        glyphs: list[bytes] = []
        count = last - first + 1
        print(f"  range U+{first:04X}..U+{last:04X} ({count}) @ {raster.px}px ...")
        for i in range(count):
            cp = first + i
            if ((i + 1) % 200) == 0:
                print(f"    ... {i + 1}/{count}")
            if 0xFB50 <= cp <= 0xFEFC and cp in raster.cmap:
                glyphs.append(raster.render_cp(cp))
            elif pres and cp in pres and _blob_has_ink(pres[cp]):
                glyphs.append(pres[cp])
            else:
                glyphs.append(raster.render_cp(cp))
        sections.append((first, last, glyphs))
    return _pack_ufl_sections(sections, raster.px)


def build_block_sparse_cps(
    raster: FontRaster,
    cps: list[int],
    pres: dict[int, bytes] | None = None,
    label: str = "sparse",
) -> bytes:
    """
    Sparse UFL: only listed codepoints that rasterize with ink (or U+0020).
    Sections = contiguous Unicode runs. No empty placeholders.
    """
    kept: list[int] = []
    blobs: dict[int, bytes] = {}
    for cp in cps:
        if pres and cp in pres and _blob_has_ink(pres[cp]):
            blob = pres[cp]
        else:
            blob = raster.render_cp(cp)
        # ASCII digit missing in FA cmap: reuse Extended Arabic-Indic digit ink
        # so UN637-style remap U+06F0..06F9 → '0'..'9' finds FR glyphs.
        if (
            0x0030 <= cp <= 0x0039
            and not _blob_has_ink(blob)
        ):
            alt = 0x06F0 + (cp - 0x0030)
            if pres and alt in pres and _blob_has_ink(pres[alt]):
                blob = pres[alt]
            else:
                blob = raster.render_cp(alt)
        if cp == 0x0020 or _blob_has_ink(blob):
            kept.append(cp)
            blobs[cp] = blob
    if not kept:
        raise ValueError(f"{label}: no glyphs to pack")
    runs = _cps_to_runs(kept)
    if len(runs) > 255:
        raise ValueError(
            f"{label}: too many section runs ({len(runs)} > 255); "
            "narrow custom ranges or use denser font coverage"
        )
    print(f"  {label}: {len(kept)} glyphs, {len(runs)} section runs @ {raster.px}px")
    sections: list[tuple[int, int, list[bytes]]] = []
    for first, last in runs:
        glyphs = [blobs[cp] for cp in range(first, last + 1)]
        sections.append((first, last, glyphs))
        print(f"    run U+{first:04X}..U+{last:04X} ({last - first + 1})")
    return _pack_ufl_sections(sections, raster.px)


def build_block_guitool_like(
    raster: FontRaster,
    pres: dict[int, bytes] | None,
    whitelist: list[int] | None = None,
) -> bytes:
    """Legacy: whitelist or fixed guitool-ish ranges → sparse pack."""
    cps = collect_guitool_like_cps(raster, pres, whitelist=whitelist)
    return build_block_sparse_cps(raster, cps, pres, label="guitool-like")


def _s8(b: int) -> int:
    return b - 256 if b & 0x80 else b


def ufl_iter_glyphs(block: bytes):
    """Yield (cp, w, h, x_off, y_off, dwidth, bitmap) for every glyph in one UFL block."""
    if len(block) < 40 or block[0:3] != b"UFL":
        return
    nsec = block[13]
    head = 40
    for i in range(nsec):
        so = head + i * 8
        first, last = struct.unpack_from("<HH", block, so)
        idx = struct.unpack_from("<I", block, so + 4)[0]
        for cp in range(first, last + 1):
            goff = struct.unpack_from("<I", block, idx + (cp - first) * 4)[0]
            if goff + 7 > len(block):
                continue
            w, h = block[goff], block[goff + 1]
            xo, yo = _s8(block[goff + 2]), _s8(block[goff + 3])
            dw = block[goff + 4]
            nbytes = struct.unpack_from("<H", block, goff + 5)[0]
            if goff + 7 + nbytes > len(block):
                continue
            bits = block[goff + 7 : goff + 7 + nbytes]
            yield cp, w, h, xo, yo, dw, bits


def _blit_1bpp(
    img: Image.Image,
    bits: bytes,
    w: int,
    h: int,
    dx: int,
    dy: int,
    scale: int,
    ink: tuple[int, int, int] = (20, 40, 120),
) -> None:
    pitch = (w + 7) // 8
    px = img.load()
    for y in range(h):
        for x in range(w):
            bi = y * pitch + (x // 8)
            if bi >= len(bits):
                continue
            if bits[bi] & (1 << (7 - (x % 8))):
                for sy in range(scale):
                    for sx in range(scale):
                        xx, yy = dx + x * scale + sx, dy + y * scale + sy
                        if 0 <= xx < img.size[0] and 0 <= yy < img.size[1]:
                            px[xx, yy] = ink


def _glyph_ink_pixels(w: int, h: int, bits: bytes) -> int:
    """Count set pixels in 1bpp MSB-first glyph bitmap."""
    if w <= 0 or h <= 0 or not bits:
        return 0
    pitch = (w + 7) // 8
    n = 0
    for y in range(h):
        for x in range(w):
            bi = y * pitch + (x // 8)
            if bi < len(bits) and (bits[bi] & (1 << (7 - (x % 8)))):
                n += 1
    return n


def _glyph_has_ink(w: int, h: int, bits: bytes) -> bool:
    """Skip empty / near-empty UFL placeholders (need a few real ink pixels)."""
    # Placeholders are often 1x1 zero, or tall blank cells with no bits set.
    return _glyph_ink_pixels(w, h, bits) >= 4


def render_ufl_preview(block: bytes, tag: str, out_png: Path, scale: int = 2) -> None:
    """One PNG per UFL block: atlas of glyphs that have ink (skip empty slots)."""
    if len(block) < 22:
        return
    font_h = max(8, int(block[20]))
    all_glyphs = list(ufl_iter_glyphs(block))
    glyphs = [g for g in all_glyphs if _glyph_has_ink(g[1], g[2], g[6])]
    skipped = len(all_glyphs) - len(glyphs)
    if not glyphs:
        return

    # Cell fits ink + small pad; cols keep FR atlases readable.
    cell = max(font_h + 6, max((g[1] for g in glyphs), default=font_h) + 4)
    cols = 32 if len(glyphs) > 128 else 16
    rows = (len(glyphs) + cols - 1) // cols
    title_h = 22
    img_w = cols * cell * scale
    img_h = title_h + rows * cell * scale
    max_side = 8000
    if img_w > max_side or img_h > max_side:
        scale = max(1, scale * max_side // max(img_w, img_h))
        img_w = cols * cell * scale
        img_h = title_h + rows * cell * scale

    img = Image.new("RGB", (img_w, img_h), (245, 245, 245))
    draw = ImageDraw.Draw(img)
    draw.text(
        (4, 4),
        f"{tag}  ink {len(glyphs)}/{len(all_glyphs)}  (skip empty {skipped})  cell={font_h}px",
        fill=(60, 60, 60),
    )

    for i, (_cp, w, h, xo, yo, _dw, bits) in enumerate(glyphs):
        col, row = i % cols, i // cols
        ox = col * cell * scale
        oy = title_h + row * cell * scale
        draw.rectangle(
            [ox, oy, ox + cell * scale - 1, oy + cell * scale - 1],
            outline=(220, 220, 220),
            fill=(255, 255, 255),
        )
        gy = oy + max(0, (font_h - yo - h)) * scale
        gx = ox + max(0, xo) * scale
        _blit_1bpp(img, bits, w, h, gx, gy, scale)

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png)


def merge_section_files(parts: list[Path], out: Path) -> int:
    """Concatenate section blobs in list order. Filenames are not validated."""
    if not parts:
        print("No section files given", file=sys.stderr)
        return 1
    blobs: list[bytes] = []
    for p in parts:
        if not p.is_file():
            print(f"Missing section file: {p}", file=sys.stderr)
            return 1
        data = p.read_bytes()
        blobs.append(data)
        print(f"  + [{len(blobs)}] {p} ({len(data)} bytes)")
    pkg = b"".join(blobs)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pkg)
    print(f"Wrote {out} ({len(pkg)} bytes) from {len(blobs)} section(s)")
    print("Hint: device expects order EN16|EN24|FR16|FR24|EN20|FR20[+FR16_B|FR24_B|FR20_B]")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Bake probe UFL (scheme A: EN=ASCII, FR=cmap-full sparse by default)"
    )
    ap.add_argument("--font", type=Path, default=DEFAULT_FA_FONT, help="Persian/FR family A TTF (Yekan)")
    ap.add_argument(
        "--font-b",
        type=Path,
        default=None,
        help="Optional Persian/FR family B TTF (prefer IRANYekanX; IranSans OK). "
        "Appends FR16_B|FR24_B|FR20_B after shared EN+FR_A package.",
    )
    ap.add_argument("--en-font", type=Path, default=DEFAULT_EN_FONT, help="Western/EN TTF (Arial)")
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--threshold", type=int, default=128, help="Gray threshold 0..255 (ink if >=)")
    ap.add_argument("--no-preview", action="store_true", help="Skip PNG previews for each block")
    ap.add_argument(
        "--fr-ranges",
        type=str,
        default=None,
        help="Custom FR Unicode ranges (FR only). Text: '0600-06FF' lines/commas. "
        "Omit = cmap-full sparse.",
    )
    ap.add_argument(
        "--fr-ranges-file",
        type=Path,
        default=None,
        help="Same as --fr-ranges but read from a UTF-8 text file",
    )
    ap.add_argument(
        "--dense-fr",
        action="store_true",
        help="Legacy: dense FR ranges with empty placeholders (larger bin)",
    )
    ap.add_argument(
        "--guitool-fr",
        action="store_true",
        help="Legacy: FR like guitool fixed ranges (sparse)",
    )
    ap.add_argument(
        "--fr-match-bdf",
        type=Path,
        default=None,
        help="Legacy: restrict FR to ENCODING list from guitool .bdf",
    )
    ap.add_argument(
        "--merge",
        nargs="+",
        type=Path,
        default=None,
        metavar="SECTION",
        help="Concatenate section files in the given order (any filenames). "
        "Skips TTF bake. Example: --merge a.bin b.bin c.bin --out font_lib.bin",
    )
    args = ap.parse_args()

    if args.merge is not None:
        return merge_section_files(list(args.merge), args.out)

    if not args.font.is_file():
        print(f"FA font A not found: {args.font}", file=sys.stderr)
        return 1
    if not args.en_font.is_file():
        print(f"EN font not found: {args.en_font}", file=sys.stderr)
        return 1
    font_b: Path | None = args.font_b
    if font_b is not None and not font_b.is_file():
        print(f"FA font B not found: {font_b}", file=sys.stderr)
        return 1

    use_guitool_fr = bool(args.guitool_fr or args.fr_match_bdf)
    fr_whitelist: list[int] | None = None
    if args.fr_match_bdf is not None:
        if not args.fr_match_bdf.is_file():
            print(f"BDF not found: {args.fr_match_bdf}", file=sys.stderr)
            return 1
        fr_whitelist = load_bdf_encodings(args.fr_match_bdf)
        print(f"FR whitelist from BDF: {len(fr_whitelist)} encodings ({args.fr_match_bdf})")

    fr_custom_ranges: list[tuple[int, int]] | None = None
    ranges_text = args.fr_ranges
    if args.fr_ranges_file is not None:
        if not args.fr_ranges_file.is_file():
            print(f"Ranges file not found: {args.fr_ranges_file}", file=sys.stderr)
            return 1
        ranges_text = args.fr_ranges_file.read_text(encoding="utf-8")
    if ranges_text:
        try:
            fr_custom_ranges = parse_unicode_ranges(ranges_text)
        except ValueError as exc:
            print(f"Bad --fr-ranges: {exc}", file=sys.stderr)
            return 1

    mode_flags = sum(
        [
            bool(args.dense_fr),
            use_guitool_fr,
            fr_custom_ranges is not None,
        ]
    )
    if mode_flags > 1:
        print(
            "Use only one of: default cmap-full / --fr-ranges / --dense-fr / --guitool-fr",
            file=sys.stderr,
        )
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Scheme A: EN always fixed ASCII (custom ranges never affect EN).
    en_ranges = [(0x0020, 0x007E)]
    fr_ranges_dense = [(0x0020, 0x007E), (0x0600, 0x06FF), (0xFB50, 0xFEFC)]

    print(f"EN font: {args.en_font}")
    print(f"FA font A: {args.font}")
    if font_b is not None:
        print(f"FA font B: {font_b}")
    if use_guitool_fr and fr_whitelist is not None:
        fr_mode = "guitool BDF whitelist"
    elif use_guitool_fr:
        fr_mode = "guitool-like sparse"
    elif args.dense_fr:
        fr_mode = "dense (legacy)"
    elif fr_custom_ranges is not None:
        fr_mode = f"custom ranges sparse ({len(fr_custom_ranges)} ranges)"
        for lo, hi in fr_custom_ranges:
            print(f"  FR range U+{lo:04X}..U+{hi:04X}")
    else:
        fr_mode = "cmap-full sparse (default)"
    print(f"FR mode: {fr_mode}")
    print("EN mode: ASCII U+0020..U+007E (scheme A)")

    def bake_fr_block(fa_path: Path, px: int, label: str) -> bytes:
        raster = FontRaster(fa_path, px, thr=args.threshold, mono=False)
        pres = build_presentation_sources(raster)
        if use_guitool_fr:
            return build_block_guitool_like(raster, pres, whitelist=fr_whitelist)
        if args.dense_fr:
            return build_block(raster, fr_ranges_dense, pres)
        cps = collect_fr_sparse_cps(raster, fr_custom_ranges, pres)
        mode = "custom-ranges" if fr_custom_ranges is not None else "cmap-full"
        return build_block_sparse_cps(raster, cps, pres, label=f"{label}-{mode}")

    # Family A package (device layout). Optional B: FR16_B|FR24_B|FR20_B after FR20_A.
    block_specs = ((16, "EN"), (24, "EN"), (16, "FR"), (24, "FR"), (20, "EN"), (20, "FR"))
    blocks: list[bytes] = []
    names: list[str] = []
    for px, kind in block_specs:
        tag = f"{kind}{px}"
        print(f"Baking {tag}...")
        if kind == "EN":
            raster = FontRaster(args.en_font, px, thr=args.threshold, mono=True)
            blocks.append(build_block(raster, en_ranges, None))
        else:
            blocks.append(bake_fr_block(args.font, px, label="FR-A"))
        names.append(tag)

    if font_b is not None:
        for px, tag in ((16, "FR16_B"), (24, "FR24_B"), (20, "FR20_B")):
            print(f"Baking {tag}...")
            blocks.append(bake_fr_block(font_b, px, label=tag))
            names.append(tag)

    pkg = b"".join(blocks)
    args.out.write_bytes(pkg)
    layout = "EN16|EN24|FR16|FR24|EN20|FR20"
    if font_b is not None:
        layout += "|FR16_B|FR24_B|FR20_B"
    print(f"Wrote {args.out} ({len(pkg)} bytes) — {layout}")

    # Also emit each UFL block alone + PNG preview (same bytes as in the package).
    parts_dir = args.out.parent / f"{args.out.stem}_parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    for tag, blob in zip(names, blocks):
        part_path = parts_dir / f"{tag}.bin"
        part_path.write_bytes(blob)
        print(f"Wrote {part_path} ({len(blob)} bytes)")
        if not args.no_preview:
            png_path = parts_dir / f"{tag}_preview.png"
            try:
                render_ufl_preview(blob, tag, png_path)
                print(f"Wrote {png_path} (all glyphs)")
            except Exception as exc:  # noqa: BLE001
                print(f"Preview skip {tag}: {exc}", file=sys.stderr)
    print(f"Parts dir: {parts_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
