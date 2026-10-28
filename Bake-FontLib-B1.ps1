# B1 (chosen): host-side TTF -> UFL bake. Device never runs FreeType.
# Output is a UFL package for Download Probe Font / production Font download.
# Optional -FaFontB appends FR16_B|FR24_B|FR20_B (shared EN dual family).
param(
  [string]$FaFont = "",
  [string]$FaFontB = "",
  [string]$EnFont = "",
  [int]$Threshold = 128,
  [string]$OutFile = ""
)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$OutDir = Join-Path $Root "out"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

if (-not $FaFont) {
  $cand = Join-Path $Root "Yekan_New.ttf"
  if (-not (Test-Path -LiteralPath $cand)) { $cand = Join-Path $Root "Yekan_custom.ttf" }
  $FaFont = $cand
}
if (-not $FaFontB) {
  # Dual family pair that matched the Old-overlap bake (~116KB): Yekan + IranSans.
  $candB = Join-Path $Root "IRAN_Sans_Regular_zitidao.ttf"
  if (Test-Path -LiteralPath $candB) { $FaFontB = $candB }
}
if (-not $EnFont) {
  $EnFont = Join-Path $env:WINDIR "Fonts\arial.ttf"
}
if (-not $OutFile) {
  $OutFile = Join-Path $OutDir "ttf_spike_font_lib.bin"
}

if (-not (Test-Path -LiteralPath $FaFont)) { throw "FA TTF A not found: $FaFont" }
if (-not (Test-Path -LiteralPath $EnFont)) { throw "EN TTF not found: $EnFont" }
if ($FaFontB -and -not (Test-Path -LiteralPath $FaFontB)) { throw "FA TTF B not found: $FaFontB" }

Write-Host "=== Font Lib B1 (PC bake only) ==="
Write-Host "EN:   $EnFont"
Write-Host "FA_A: $FaFont"
if ($FaFontB) { Write-Host "FA_B: $FaFontB" } else { Write-Host "FA_B: (none — single family)" }
Write-Host "Out:  $OutFile"

$bakeArgs = @(
  "-3", "-u", (Join-Path $Root "Bake-TtfToUfl.py"),
  "--font", $FaFont,
  "--en-font", $EnFont,
  "--threshold", "$Threshold",
  "--out", $OutFile
)
if ($FaFontB) {
  $bakeArgs += @("--font-b", $FaFontB)
}

& py @bakeArgs
if ($LASTEXITCODE -ne 0) { throw "Bake-TtfToUfl.py failed ($LASTEXITCODE)" }

# Convenience copy for production Font-page rename (does not auto-install on device).
$prodCopy = Join-Path $OutDir "font_lib_from_ttf.bin"
Copy-Item -LiteralPath $OutFile -Destination $prodCopy -Force

$len = (Get-Item -LiteralPath $OutFile).Length
$layout = "EN16|EN24|FR16|FR24|EN20|FR20"
if ($FaFontB) { $layout += "|FR16_B|FR24_B|FR20_B" }
Write-Host ""
Write-Host "B1 OK: $OutFile ($len bytes)  $layout"
Write-Host "Also:  $prodCopy"
Write-Host ""
Write-Host "Next on device:"
Write-Host "  Probe A/B : Update Firmware -> Download Probe Font  (send ttf_spike_font_lib.bin)"
Write-Host "  Production: Update Firmware -> Download Font Lib   (send font_lib_from_ttf.bin as Font)"
Write-Host "              -> /mnt/flash/font_lib.bin + RAM Adopt (new proto L/A or legacy T/S)"
Write-Host "  Dual family: Update Firmware -> Font Family A/B"
Write-Host "Device runtime stays UFL/GetFont; no on-device FreeType (B2 deferred)."
