# On-device Font Probe / Production Font Lib

**Plan lock: B1** — bake TTF→UFL on PC; device filesystem holds **UFL only** (no on-device FreeType / B2 deferred).

Resident UI uses `/mnt/flash/font_lib.bin` (UFL). Probe uses a **separate** file so you can A/B without replacing production.

## Paths

| Item | Path / API |
|------|------------|
| Macro | `ENABLE_FONT_DOWNLOAD=1`, `ENABLE_FONT_PROBE=1`, `USE_NEW_DOWNLOAD_PROTOCOL=1` |
| Production | `/mnt/flash/font_lib.bin` ← **Download Font Lib** |
| Probe file | `/mnt/flash/ttf_probe_font.bin` ← **Download Probe Font** |
| APIs | `FontLib_ShowOrFallback` / `FontProbe_Load` / `UsbFileDl_ServeFontLibFromPc` / `ServeFontProbeFromPc` |
| PC bake | `Bake-FontLib-B1.ps1` → `out\ttf_spike_font_lib.bin` + `out\font_lib_from_ttf.bin` |

Frozen bake (2026-10-26): FR `thr×3/4`, floor advance, `dwidth ≤ ink_right+1`, dual **Yekan + IranSans**, package **116717 B**. WIP backup: `_backup_font_20261026_205908/` (no git commit).

## Production download (item 2)

Preferred when `USE_NEW_DOWNLOAD_PROTOCOL=1`:

1. Bake:
   ```powershell
   cd device\tools\ttf_1bpp_spike
   powershell -ExecutionPolicy Bypass -File .\Bake-FontLib-B1.ps1
   ```
2. Device: **Update Firmware → Download Font Lib**
3. PC LoadTool: send **Font** type with `out\font_lib_from_ttf.bin` (same bytes as probe bin).
4. Device commits to `/mnt/flash/font_lib.bin`, validates UFL, **Adopt** into resident RAM.
5. Confirm: LCD shows Download OK / `font_lib.bin saved`; **Font Family A/B** and normal UI use the new lib after bind (reboot also reloads from FS).

Also accepted on the same menu:

- Legacy LoadTool Font pages (`T/S` + `0xB0/0xB1`) via `UsbDownloadFontLibAfterTs`.

Alternate (multi-file session): **Download file from PC** with type Font → same `install_font()` → `FONT_LIB_PATH` (not probe).

## Probe A/B (does not touch production)

1. **Download Probe Font** — send `ttf_spike_font_lib.bin` → `ttf_probe_font.bin`.
2. **Font Probe Compare** — LCD 16→20→24 then print; CANCEL exits.
3. When Probe OK → use **Download Font Lib** with `font_lib_from_ttf.bin` (above).

## Checklist

- [ ] Probe download does **not** replace `font_lib.bin`.
- [ ] Production Download Font Lib **does** replace `font_lib.bin` and binds RAM.
- [ ] Dual package: Family A/B menu works after production download.
- [ ] Delete Font Lib removes FS file and falls back cleanly.
- [ ] Do **not** put raw `.ttf` on device for LCD/print under B1.
