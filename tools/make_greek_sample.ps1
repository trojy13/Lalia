# Writes a Greek test recording with the Windows "Microsoft Stefanos" voice, so the
# recognition pipeline can be checked without a microphone:
#   powershell -ExecutionPolicy Bypass -File tools\make_greek_sample.ps1 -Out samples\el.wav -Text "..."
# Needs the Greek speech voice (Settings > Time & language > Speech > Add voices).
# -English speaks the text with the desktop English voice (System.Speech) instead.
param(
    [Parameter(Mandatory = $true)][string]$Out,
    [string]$Text = "Καλημέρα σας. Η συνταγή περιλαμβάνει δύο κουτιά αμοξικιλλίνη και ένα σιρόπι για τον βήχα. Παρακαλώ ελέγξτε τη διαθεσιμότητα στην αποθήκη.",
    [switch]$English
)
$ErrorActionPreference = "Stop"
$full = [IO.Path]::GetFullPath($Out)
$dir = Split-Path -Parent $full
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
if ($English) {
    Add-Type -AssemblyName System.Speech
    $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like "en-*" } | Select-Object -First 1
    if (-not $v) { throw "No English desktop voice is installed." }
    $s.SelectVoice($v.VoiceInfo.Name)
    $s.SetOutputToWaveFile($full)
    $s.Speak($Text)
    $s.Dispose()
    Write-Output "wrote $Out (voice $($v.VoiceInfo.Name))"
    return
}
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.DataReader, Windows.Storage.Streams, ContentType = WindowsRuntime]

$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq "AsTask" -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
function Await($op, [Type]$type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
    [void]$task.Wait(-1)
    $task.Result
}

$synth = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
$voice = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices | Where-Object { $_.Language -eq "el-GR" } | Select-Object -First 1
if (-not $voice) { throw "No Greek (el-GR) speech voice is installed." }
$synth.Voice = $voice
$stream = Await ($synth.SynthesizeTextToStreamAsync($Text)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
$size = [uint32]$stream.Size
$reader = New-Object Windows.Storage.Streams.DataReader($stream.GetInputStreamAt(0))
[void](Await ($reader.LoadAsync($size)) ([uint32]))
$bytes = New-Object byte[] $size
$reader.ReadBytes($bytes)
[IO.File]::WriteAllBytes($full, $bytes)
Write-Output "wrote $Out ($size bytes, voice $($voice.DisplayName))"
