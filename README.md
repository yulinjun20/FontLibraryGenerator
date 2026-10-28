# TTF 1bpp spike (step 2 of TTF plan)

## Purpose

Device OS currently has **no** FreeType/`cz_font` linked for LCD/printer (`CONFIG_FONT_SUPPORT` off, `libfont.a` missing).
This PC tool approximates the **glyph provider contract** used by LCD/printer:

- 1bpp, MSB-first (`1 << (7 - x%8)`)
- row pitch = ceil(width / 8)
- height targets **16 / 20 / 24** (device caps height ~48)

Use the PNG previews to judge **display/print-like** sharpness after thresholding **before** wiring FreeType on device.

## Run

```powershell
cd device\tools\ttf_1bpp_spike
powershell -ExecutionPolicy Bypass -File .\Render-Ttf1bppSpike.ps1
# optional:
powershell -ExecutionPolicy Bypass -File .\Render-Ttf1bppSpike.ps1 -Threshold 140 -FontPath C:\Windows\Fonts\arial.ttf
```

Outputs under `out/`:

- `*_preview.png` — zoomed 1bpp preview (look for broken strokes / fat blobs)
- `*.1bpp.bin` — raw packed bits
- `metrics.csv` — width/pitch/size

## How to judge (vs current UFL)

| Check | Pass hint |
|-------|-----------|
| Latin 16/20/24 | Edges readable, no broken thin strokes |
| Amounts / punctuation | Baseline stable |
| Persian sample (Tahoma) | Digits/letters not fused after threshold |
| thr 128 vs 140 | Pick better; printer often wants slightly lower thr (fatter ink) |

## Chosen path: B1 (host bake → device UFL only)

Device does **not** run FreeType. PC bakes TTF → UFL; download the `.bin` like today’s Font / Probe Font.

```powershell
cd device\tools\ttf_1bpp_spike
py -3 -m pip install uharfbuzz freetype-py fonttools pillow
# GUI (pick EN/FA TTF, output path, Bake):
py -3 .\Bake-TtfToUfl-Gui.py
# or CLI one-shot:
powershell -ExecutionPolicy Bypass -File .\Bake-FontLib-B1.ps1
# → out\ttf_spike_font_lib.bin (+ font_lib_from_ttf.bin)
# → out\ttf_spike_font_lib_parts\EN16.bin … FR20.bin
# → same folder: EN16_preview.png … FR20_preview.png (each PNG = all glyphs in that bin)
```

CLI bake only:
```powershell
# Default (scheme A): EN=ASCII, FR=cmap-full sparse (no empty slots)
py -3 -u .\Bake-TtfToUfl.py --font Yekan_New.ttf
# Dual family (shared EN + FR_A + FR_B trailer):
py -3 -u .\Bake-TtfToUfl.py --font Yekan_New.ttf --font-b IranSans.ttf
# Custom FR ranges only (EN still ASCII):
py -3 -u .\Bake-TtfToUfl.py --font Yekan_New.ttf --fr-ranges "0600-06FF,FB50-FEFC"
# Legacy dense FR (empty placeholders; larger bin):
py -3 -u .\Bake-TtfToUfl.py --font Yekan_New.ttf --dense-fr
# Legacy guitool-like / BDF whitelist:
py -3 -u .\Bake-TtfToUfl.py --font Yekan_New.ttf --guitool-fr
py -3 -u .\Bake-TtfToUfl.py --font Yekan_New.ttf --fr-match-bdf E:\MyProject\UN650\ML160T\UN650Font\test\Yekan_New_U20.bdf
```

**Fallback (GDI only, weaker joining):** `Bake-TtfToUfl.ps1`

| Block | Content |
|-------|---------|
| EN16/EN24/EN20 | ASCII `0x20..0x7E` (scheme A; shared by both families) |
| FR16/FR24/FR20 | Family A (e.g. Yekan). cmap-full sparse by default. |
| FR16_B/FR24_B/FR20_B | Optional family B (e.g. IranSans) when `--font-b` set. |

Device: `Lib_FontSetFamily(FONT_CHANNEL_LCD|PRN, FONT_FAMILY_A|B)` / `DLL_FontSetFamily`.
Old 6-block libs remain valid (no B trailer → B select returns unsupported).

Factory check: **Update Firmware → Font Family A/B** (needs dual bin via Download Font Lib or Probe).
Default B1 bake auto-picks `IRAN_Sans_Regular_zitidao.ttf` as family B when present.

Compare: LCD **16 → 20 → 24** then print. Device FriBidi + ConvertRule*; HarfBuzz is **PC bake only**.  
Deferred: B2 (on-device bake), runtime TTF (scheme A).

## Next after review

- **Effect OK** → Download Font Lib with `out\font_lib_from_ttf.bin` to replace production `font_lib.bin`.
- **Effect NOT OK** → tune threshold / TTF on PC and re-run `Bake-FontLib-B1.ps1`.
