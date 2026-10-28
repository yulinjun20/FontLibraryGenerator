# TTF -> 1bpp spike (matches LCD/printer packing contract)
#
# Device Unicode path expects:
#   sbn_glyph_t (8B on wire after pad) + 1bpp MSB-first rows, pitch=ceil(width/8)
# This tool: GDI render -> threshold -> pack -> PNG preview (8x zoom) + metrics CSV.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File Render-Ttf1bppSpike.ps1
#   powershell -ExecutionPolicy Bypass -File Render-Ttf1bppSpike.ps1 -FontPath "C:\Windows\Fonts\arial.ttf" -Threshold 140

param(
  [string]$FontPath = "$env:WINDIR\Fonts\arial.ttf",
  [string]$PersianFontPath = "$env:WINDIR\Fonts\tahoma.ttf",
  [string]$OutDir = "",
  [int]$Threshold = 128,
  [int]$Zoom = 8
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

if (-not $OutDir) {
  $OutDir = Join-Path $PSScriptRoot "out"
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

function Pack-1bppMsb([System.Drawing.Bitmap]$bmp, [int]$thr) {
  $w = $bmp.Width; $h = $bmp.Height
  $pitch = [Math]::Ceiling($w / 8.0)
  $bytes = New-Object byte[] ($pitch * $h)
  for ($y = 0; $y -lt $h; $y++) {
    for ($x = 0; $x -lt $w; $x++) {
      $c = $bmp.GetPixel($x, $y)
      # luminance; ink if dark enough
      $lum = [int](0.299*$c.R + 0.587*$c.G + 0.114*$c.B)
      if ($lum -lt $thr) {
        $bi = $y * $pitch + [Math]::Floor($x / 8)
        $bit = 7 - ($x % 8)
        $bytes[$bi] = $bytes[$bi] -bor (1 -shl $bit)
      }
    }
  }
  return @{
    'Bytes'  = $bytes
    'Pitch'  = [int]$pitch
    'Width'  = [int]$w
    'Height' = [int]$h
  }
}

function Unpack-ToBitmap($pack, [int]$zoom) {
  $w = [int]$pack['Width']; $h = [int]$pack['Height']; $pitch = [int]$pack['Pitch']; $bytes = $pack['Bytes']
  $bmp = New-Object System.Drawing.Bitmap ([int]($w * $zoom), [int]($h * $zoom))
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.Clear([System.Drawing.Color]::White)
  $brush = [System.Drawing.Brushes]::Black
  for ($y = 0; $y -lt $h; $y++) {
    for ($x = 0; $x -lt $w; $x++) {
      $bi = $y * $pitch + [Math]::Floor($x / 8)
      $bit = 7 - ($x % 8)
      if (($bytes[$bi] -band (1 -shl $bit)) -ne 0) {
        $g.FillRectangle($brush, $x*$zoom, $y*$zoom, $zoom, $zoom)
      }
    }
  }
  $g.Dispose()
  return $bmp
}

function Render-Line([string]$text, [string]$fontFile, [int]$pxHeight, [int]$thr) {
  if (-not (Test-Path -LiteralPath $fontFile)) {
    throw "Font not found: $fontFile"
  }
  # Em size in pixels ~ height; GDI PrivateFontCollection for TTF path
  $pfc = New-Object System.Drawing.Text.PrivateFontCollection
  $pfc.AddFontFile($fontFile)
  $ff = $pfc.Families[0]
  $font = New-Object System.Drawing.Font($ff, [single]$pxHeight, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)

  # Measure
  $tmp = New-Object System.Drawing.Bitmap 8, 8
  $g0 = [System.Drawing.Graphics]::FromImage($tmp)
  $g0.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
  $sz = $g0.MeasureString($text, $font)
  $g0.Dispose(); $tmp.Dispose()

  $w = [Math]::Max(1, [int][Math]::Ceiling($sz.Width) + 2)
  $h = [Math]::Max($pxHeight, [int][Math]::Ceiling($sz.Height) + 2)
  if ($w -gt 400) { $w = 400 }
  if ($h -gt 48) { $h = 48 }  # device glyph height cap

  $bmp = New-Object System.Drawing.Bitmap $w, $h
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.Clear([System.Drawing.Color]::White)
  $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
  $g.DrawString($text, $font, [System.Drawing.Brushes]::Black, 0, 0)
  $g.Dispose()
  $font.Dispose()
  $pfc.Dispose()

  $pack = Pack-1bppMsb $bmp $thr
  $bmp.Dispose()
  return $pack
}

$samples = @(
  @{ Name = "en_ascii"; Font = $FontPath; Text = "ABCxyz 0123 `$.,!?" },
  @{ Name = "en_mix";   Font = $FontPath; Text = "Sale 12,500 IRR" },
  @{ Name = "fa_digit"; Font = $PersianFontPath; Text = ([char]0x06F1).ToString() + ([char]0x06F2) + ([char]0x06F3) + " " + ([char]0x0622) + ([char]0x0632) + ([char]0x0645) + ([char]0x0627) + ([char]0x06CC) + ([char]0x0634) }
)

$heights = @(16, 20, 24)
$csv = New-Object System.Collections.Generic.List[string]
$csv.Add("sample,height,font,width,pitch,bytes,threshold,png")

foreach ($s in $samples) {
  $fontUse = $s.Font
  if (-not (Test-Path -LiteralPath $fontUse)) {
    Write-Warning "Skip $($s.Name): missing $fontUse"
    continue
  }
  foreach ($h in $heights) {
    $pack = Render-Line $s.Text $fontUse $h $Threshold
    $tag = "{0}_h{1}" -f $s.Name, $h
    $rawPath = Join-Path $OutDir ($tag + ".1bpp.bin")
    [IO.File]::WriteAllBytes($rawPath, $pack['Bytes'])

    $prev = Unpack-ToBitmap $pack $Zoom
    # banner with metrics
    $bannerH = 24
    $sheet = New-Object System.Drawing.Bitmap ([int]$prev.Width, [int]($prev.Height + $bannerH))
    $gs = [System.Drawing.Graphics]::FromImage($sheet)
    $gs.Clear([System.Drawing.Color]::White)
    $gs.DrawImage($prev, 0, $bannerH)
    $msg = "{0} w={1} pitch={2} bytes={3} thr={4}" -f $tag, $pack['Width'], $pack['Pitch'], $pack['Bytes'].Length, $Threshold
    $gs.DrawString($msg, (New-Object System.Drawing.Font("Consolas", 10)), [System.Drawing.Brushes]::Black, 2, 2)
    $gs.Dispose()
    $pngPath = Join-Path $OutDir ($tag + "_preview.png")
    $sheet.Save($pngPath, [System.Drawing.Imaging.ImageFormat]::Png)
    $sheet.Dispose(); $prev.Dispose()

    $csv.Add(("{0},{1},{2},{3},{4},{5},{6},{7}" -f $s.Name, $h, (Split-Path $fontUse -Leaf), $pack['Width'], $pack['Pitch'], $pack['Bytes'].Length, $Threshold, $pngPath))
    Write-Host "OK $tag -> $pngPath"
  }
}

$csvPath = Join-Path $OutDir "metrics.csv"
$csv | Set-Content -Encoding UTF8 $csvPath
Write-Host "Wrote $csvPath"
Write-Host "Compare these previews vs device UFL glyphs at same heights."
