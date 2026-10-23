param([string]$Dir, [string]$Out)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$t) { $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op)); $task.Wait(-1) | Out-Null; $task.Result }
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
$engine = $null
try { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('en-US')) } catch {}
if (-not $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
$res = @()
Get-ChildItem $Dir -File | Where-Object { $_.Extension -in '.png', '.jpg' } | Sort-Object Name | ForEach-Object {
  try {
    $f = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($_.FullName)) ([Windows.Storage.StorageFile])
    $s = Await ($f.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $d = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($s)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $b = Await ($d.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $r = Await ($engine.RecognizeAsync($b)) ([Windows.Media.Ocr.OcrResult])
    $lines = @($r.Lines | ForEach-Object { $_.Text })
    $res += [pscustomobject]@{ file = $_.Name; w = $d.PixelWidth; h = $d.PixelHeight; lines = $lines }
    $s.Dispose()
  } catch { $res += [pscustomobject]@{ file = $_.Name; error = "$_" } }
}
$json = $res | ConvertTo-Json -Depth 4
[IO.File]::WriteAllText($Out, $json, (New-Object Text.UTF8Encoding $false))
"done $($res.Count)"
