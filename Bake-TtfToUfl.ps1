# Bake EN16|EN24|FR16|FR24 UFL package from TTF for Font Probe download.
# EN: ASCII 0x20-0x7E
# FR: ASCII (remapped Persian digits) + Arabic 0x0600-0x06FF + presentation FB50-FEFC
#     (device ConvertRule* looks up presentation forms after shaping)
param(
  [string]$FontPath = "",
  [int]$Threshold = 128,
  [string]$OutFile = ""
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

$OutDir = Join-Path $PSScriptRoot "out"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
if (-not $FontPath) {
  # Prefer fuller Persian coverage; fall back to Yekan_custom.ttf.
  $cand = Join-Path $PSScriptRoot "Yekan_New.ttf"
  if (Test-Path -LiteralPath $cand) { $FontPath = $cand }
  else { $FontPath = Join-Path $PSScriptRoot "Yekan_custom.ttf" }
}
if (-not $OutFile) {
  $OutFile = Join-Path $OutDir "ttf_spike_font_lib.bin"
}
if (-not (Test-Path -LiteralPath $FontPath)) {
  throw "Font not found: $FontPath"
}

# Ink-crop 1bpp pack; returns bits, width, height, x_bearing (left crop).
function Pack-1bppCrop([System.Drawing.Bitmap]$bmp, [int]$thr) {
  $w = [int]$bmp.Width
  $h = [int]$bmp.Height
  $minX = $w; $maxX = -1; $minY = $h; $maxY = -1
  for ($y = 0; $y -lt $h; $y++) {
    for ($x = 0; $x -lt $w; $x++) {
      $c = $bmp.GetPixel($x, $y)
      $lum = [int](0.299 * $c.R + 0.587 * $c.G + 0.114 * $c.B)
      if ($lum -lt $thr) {
        if ($x -lt $minX) { $minX = $x }
        if ($x -gt $maxX) { $maxX = $x }
        if ($y -lt $minY) { $minY = $y }
        if ($y -gt $maxY) { $maxY = $y }
      }
    }
  }
  if ($maxX -lt 0) {
    # Empty / missing glyph: 1px wide blank cell.
    $cw = 1; $ch = [Math]::Max(1, $h); $xb = 0
    $pitch = 1
    $bytes = New-Object byte[] ($pitch * $ch)
    return ,@($bytes, $cw, $ch, $xb)
  }
  $cw = $maxX - $minX + 1
  $ch = $maxY - $minY + 1
  $xb = $minX
  $pitch = [int][Math]::Ceiling($cw / 8.0)
  $bytes = New-Object byte[] ($pitch * $ch)
  for ($y = 0; $y -lt $ch; $y++) {
    for ($x = 0; $x -lt $cw; $x++) {
      $c = $bmp.GetPixel($minX + $x, $minY + $y)
      $lum = [int](0.299 * $c.R + 0.587 * $c.G + 0.114 * $c.B)
      if ($lum -lt $thr) {
        $bi = $y * $pitch + [int][Math]::Floor($x / 8)
        $bit = 7 - ($x % 8)
        $bytes[$bi] = [byte]($bytes[$bi] -bor (1 -shl $bit))
      }
    }
  }
  return ,@($bytes, $cw, $ch, $xb)
}

# Device ConvertRule* maps logical Arabic/Persian → presentation forms (FE*/FB*).
# Many TTFs (incl. Yekan) omit FE* slots; fill empty presentation glyphs from logical.
function Build-PresentationFallbackMap {
  $map = @{}
  # Arbic_Position[0x621..0x64A]: first,last,middle,alone — prefer alone then first.
  $arb = @(
    @(0xfe80,0xfe80,0xfe80,0xfe80),
    @(0xfe82,0xfe81,0xfe82,0xfe81),
    @(0xfe84,0xfe83,0xfe84,0xfe83),
    @(0xfe86,0xfe85,0xfe86,0xfe85),
    @(0xfe88,0xfe87,0xfe88,0xfe87),
    @(0xfe8a,0xfe8b,0xfe8c,0xfe89),
    @(0xfe8e,0xfe8d,0xfe8e,0xfe8d),
    @(0xfe90,0xfe91,0xfe92,0xfe8f),
    @(0xfe94,0xfe93,0xfe94,0xfe93),
    @(0xfe96,0xfe97,0xfe98,0xfe95),
    @(0xfe9a,0xfe9b,0xfe9c,0xfe99),
    @(0xfe9e,0xfe9f,0xfea0,0xfe9d),
    @(0xfea2,0xfea3,0xfea4,0xfea1),
    @(0xfea6,0xfea7,0xfea8,0xfea5),
    @(0xfeaa,0xfea9,0xfeaa,0xfea9),
    @(0xfeac,0xfeab,0xfeac,0xfeab),
    @(0xfeae,0xfead,0xfeae,0xfead),
    @(0xfeb0,0xfeaf,0xfeb0,0xfeaf),
    @(0xfeb2,0xfeb3,0xfeb4,0xfeb1),
    @(0xfeb6,0xfeb7,0xfeb8,0xfeb5),
    @(0xfeba,0xfebb,0xfebc,0xfeb9),
    @(0xfebe,0xfebf,0xfec0,0xfebd),
    @(0xfec2,0xfec3,0xfec4,0xfec1),
    @(0xfec6,0xfec7,0xfec8,0xfec5),
    @(0xfeca,0xfecb,0xfecc,0xfec9),
    @(0xfece,0xfecf,0xfed0,0xfecd),
    @(0x63b,0x63b,0x63b,0x63b),
    @(0x63c,0x63c,0x63c,0x63c),
    @(0x63d,0x63d,0x63d,0x63d),
    @(0x63e,0x63e,0x63e,0x63e),
    @(0x63f,0x63f,0x63f,0x63f),
    @(0x640,0x640,0x640,0x640),
    @(0xfed2,0xfed3,0xfed4,0xfed1),
    @(0xfed6,0xfed7,0xfed8,0xfed5),
    @(0xfeda,0xfedb,0xfedc,0xfed9),
    @(0xfede,0xfedf,0xfee0,0xfedd),
    @(0xfee2,0xfee3,0xfee4,0xfee1),
    @(0xfee6,0xfee7,0xfee8,0xfee5),
    @(0xfeea,0xfeeb,0xfeec,0xfee9),
    @(0xfeee,0xfeed,0xfeee,0xfeed),
    @(0xfef0,0xfef3,0xfef4,0xfeef),
    @(0xfef2,0xfef3,0xfef4,0xfef1)
  )
  for ($i = 0; $i -lt $arb.Count; $i++) {
    $logical = 0x621 + $i
    foreach ($form in $arb[$i]) {
      if ($form -ge 0xFB50 -and $form -le 0xFEFC) {
        if (-not $map.ContainsKey($form)) { $map[$form] = $logical }
      }
    }
  }
  # Persian_AlphabetTab: last,first,middle,alone
  $per = @(
    @{ L = 0x067e; F = @(0xfb57,0xfb58,0xfb59,0xfb56) },
    @{ L = 0x0686; F = @(0xfb7b,0xfb7c,0xfb7d,0xfb7a) },
    @{ L = 0x0698; F = @(0xfb8b,0xfb8a,0xfb8b,0xfb8a) },
    @{ L = 0x06a9; F = @(0xfb8f,0xfb90,0xfb91,0xfb8e) },
    @{ L = 0x06af; F = @(0xfb93,0xfb94,0xfb95,0xfb92) },
    @{ L = 0x06cc; F = @(0xfbfd,0xfbfe,0xfbff,0xfbfc) }
  )
  foreach ($p in $per) {
    foreach ($form in $p.F) {
      if (-not $map.ContainsKey($form)) { $map[$form] = $p.L }
    }
  }
  # Lam-Alef ligatures → alef
  foreach ($form in @(0xFEF5,0xFEF6,0xFEF7,0xFEF8,0xFEF9,0xFEFA,0xFEFB,0xFEFC)) {
    if (-not $map.ContainsKey($form)) { $map[$form] = 0x0627 }
  }
  return $map
}

$script:PresFallback = Build-PresentationFallbackMap

function Render-GlyphRaw([System.Drawing.Text.PrivateFontCollection]$pfc, [int]$px, [int]$cp, [int]$thr) {
  $font = New-Object System.Drawing.Font($pfc.Families[0], [single]$px,
    [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
  $pad = [Math]::Max(4, [int]($px / 2))
  $canvasW = [Math]::Min(120, $px * 4 + $pad * 2)
  $canvasH = [Math]::Min(48, $px + $pad)
  $bmp = New-Object System.Drawing.Bitmap $canvasW, $canvasH
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.Clear([System.Drawing.Color]::White)
  $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
  $sf = New-Object System.Drawing.StringFormat
  $sf.FormatFlags = [System.Drawing.StringFormatFlags]::NoClip
  $g.DrawString([string][char]$cp, $font, [System.Drawing.Brushes]::Black, [single]$pad, 0, $sf)
  $g.Dispose()
  $font.Dispose()
  $sf.Dispose()

  $pack = Pack-1bppCrop $bmp $thr
  $bmp.Dispose()
  return $pack
}

function Render-Glyph([System.Drawing.Text.PrivateFontCollection]$pfc, [int]$px, [int]$cp, [int]$thr) {
  $pack = Render-GlyphRaw $pfc $px $cp $thr
  $bits = $pack[0]
  $bw = [int]$pack[1]
  $bh = [int]$pack[2]
  # Empty presentation form → redraw from logical Arabic/Persian letter.
  $inkBytes = 0
  foreach ($b in $bits) { if ($b -ne 0) { $inkBytes++ } }
  if (($inkBytes -eq 0 -or $bw -le 1) -and $script:PresFallback.ContainsKey($cp)) {
    $logic = [int]$script:PresFallback[$cp]
    $pack = Render-GlyphRaw $pfc $px $logic $thr
    $bits = $pack[0]
    $bw = [int]$pack[1]
    $bh = [int]$pack[2]
  }
  if ($bw -gt 100) { $bw = 100 }
  if ($bh -gt 48) { $bh = 48 }
  $dwidth = [Math]::Max(1, $bw + 1)

  $glyph = New-Object byte[] (7 + $bits.Length)
  $glyph[0] = [byte]$bw
  $glyph[1] = [byte]$bh
  $glyph[2] = 0
  $glyph[3] = 0
  $glyph[4] = [byte]$dwidth
  $glyph[5] = [byte]($bits.Length -band 0xFF)
  $glyph[6] = [byte](($bits.Length -shr 8) -band 0xFF)
  $copyLen = [Math]::Min($bits.Length, $glyph.Length - 7)
  if ($copyLen -gt 0) {
    [Array]::Copy($bits, 0, $glyph, 7, $copyLen)
  }
  return $glyph
}

# $ranges: array of @{First=..; Last=..}
function Build-Block([string]$fontFile, [int]$px, [int]$thr, [array]$ranges) {
  $pfc = New-Object System.Drawing.Text.PrivateFontCollection
  $pfc.AddFontFile($fontFile)

  $secList = New-Object System.Collections.Generic.List[hashtable]
  $totalCount = 0
  foreach ($r in $ranges) {
    $first = [int]$r.First
    $last = [int]$r.Last
    $count = $last - $first + 1
    Write-Host ("  range U+{0:X4}..U+{1:X4} ({2} glyphs) @ {3}px ..." -f $first, $last, $count, $px)
    $glyphs = New-Object object[] $count
    for ($i = 0; $i -lt $count; $i++) {
      $glyphs[$i] = Render-Glyph $pfc $px ($first + $i) $thr
      if ((($i + 1) % 200) -eq 0) {
        Write-Host ("    ... {0}/{1}" -f ($i + 1), $count)
      }
    }
    $secList.Add(@{ First = $first; Last = $last; Glyphs = $glyphs })
    $totalCount += $count
  }
  $pfc.Dispose()

  $nSection = $secList.Count
  $headSize = 40
  $secTableBytes = $nSection * 8
  $indexOff = $headSize + $secTableBytes
  $indexBytes = $totalCount * 4
  $dataOff = $indexOff + $indexBytes

  $ms = New-Object System.IO.MemoryStream
  $bw = New-Object System.IO.BinaryWriter $ms
  $bw.Write((New-Object byte[] $dataOff))

  $allOffs = New-Object System.Collections.Generic.List[int]
  foreach ($sec in $secList) {
    foreach ($g in $sec.Glyphs) {
      $allOffs.Add([int]$ms.Position)
      $bw.Write([byte[]]$g)
    }
  }
  $fileSize = [int]$ms.Length
  $buf = $ms.ToArray()
  $bw.Close(); $ms.Close()

  $buf[0] = 0x55; $buf[1] = 0x46; $buf[2] = 0x4C; $buf[3] = 0x81
  [BitConverter]::GetBytes([uint32]$fileSize).CopyTo($buf, 4)
  [BitConverter]::GetBytes([uint32]$headSize).CopyTo($buf, 8)
  $buf[12] = 0
  $buf[13] = [byte]$nSection
  [BitConverter]::GetBytes([uint16]1).CopyTo($buf, 14)
  [BitConverter]::GetBytes([int32]1).CopyTo($buf, 16)
  $buf[20] = [byte]$px; $buf[21] = [byte]$px
  [BitConverter]::GetBytes([int32]($px - 2)).CopyTo($buf, 24)
  [BitConverter]::GetBytes([int32]2).CopyTo($buf, 28)
  [BitConverter]::GetBytes([int32]$totalCount).CopyTo($buf, 32)
  [BitConverter]::GetBytes([int32]$totalCount).CopyTo($buf, 36)

  $gi = 0
  for ($s = 0; $s -lt $nSection; $s++) {
    $sec = $secList[$s]
    $so = $headSize + $s * 8
    [BitConverter]::GetBytes([uint16]$sec.First).CopyTo($buf, $so)
    [BitConverter]::GetBytes([uint16]$sec.Last).CopyTo($buf, $so + 2)
    # OffAddr = start of this section's index entries
    $secIndexOff = $indexOff + $gi * 4
    [BitConverter]::GetBytes([uint32]$secIndexOff).CopyTo($buf, $so + 4)
    $cnt = $sec.Last - $sec.First + 1
    for ($i = 0; $i -lt $cnt; $i++) {
      [BitConverter]::GetBytes([uint32]$allOffs[$gi + $i]).CopyTo($buf, $secIndexOff + $i * 4)
    }
    $gi += $cnt
  }

  Write-Host ("block px={0} nSec={1} glyphs={2} size={3}" -f $px, $nSection, $totalCount, $fileSize)
  return $buf
}

$enRanges = @(
  @{ First = 0x0020; Last = 0x007E }
)
# Match device shaping needs: remapped digits in ASCII FR, logical Arabic, presentation forms.
$frRanges = @(
  @{ First = 0x0020; Last = 0x007E },
  @{ First = 0x0600; Last = 0x06FF },
  @{ First = 0xFB50; Last = 0xFEFC }
)

Write-Host "Font: $FontPath"
Write-Host "Baking EN16..."
$en16 = Build-Block $FontPath 16 $Threshold $enRanges
Write-Host "Baking EN24..."
$en24 = Build-Block $FontPath 24 $Threshold $enRanges
Write-Host "Baking FR16 (ASCII+Arabic+presentation)..."
$fr16 = Build-Block $FontPath 16 $Threshold $frRanges
Write-Host "Baking FR24 (ASCII+Arabic+presentation)..."
$fr24 = Build-Block $FontPath 24 $Threshold $frRanges
# Optional U20 chain (device Compare uses 20px): EN20 then FR20 after FR24.
Write-Host "Baking EN20..."
$en20 = Build-Block $FontPath 20 $Threshold $enRanges
Write-Host "Baking FR20 (ASCII+Arabic+presentation)..."
$fr20 = Build-Block $FontPath 20 $Threshold $frRanges

$pkg = New-Object byte[] ($en16.Length + $en24.Length + $fr16.Length + $fr24.Length + $en20.Length + $fr20.Length)
$o = 0
[Array]::Copy($en16, 0, $pkg, $o, $en16.Length); $o += $en16.Length
[Array]::Copy($en24, 0, $pkg, $o, $en24.Length); $o += $en24.Length
[Array]::Copy($fr16, 0, $pkg, $o, $fr16.Length); $o += $fr16.Length
[Array]::Copy($fr24, 0, $pkg, $o, $fr24.Length); $o += $fr24.Length
[Array]::Copy($en20, 0, $pkg, $o, $en20.Length); $o += $en20.Length
[Array]::Copy($fr20, 0, $pkg, $o, $fr20.Length)

[IO.File]::WriteAllBytes($OutFile, $pkg)
Write-Host ("Wrote {0} ({1} bytes) — EN16|EN24|FR16|FR24|EN20|FR20; Download Probe Font" -f $OutFile, $pkg.Length)
