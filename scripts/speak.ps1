param([Parameter(Mandatory=$true)][string]$RequestPath)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$taskRequest = Get-Content -LiteralPath $RequestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$taskVoice = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $taskVoice.SelectVoice($taskRequest.voice)
    $taskVoice.Rate = [int]$taskRequest.rate
    $taskVoice.SetOutputToWaveFile($taskRequest.out)
    $taskVoice.Speak($taskRequest.text)
} finally {
    $taskVoice.Dispose()
}
