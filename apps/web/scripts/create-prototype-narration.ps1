$ErrorActionPreference = 'Stop'
$prototypeAudioPath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../public/demo/narration.wav'))
$prototypeStream = New-Object -ComObject SAPI.SpFileStream
$prototypeSpeaker = New-Object -ComObject SAPI.SpVoice
try {
  $prototypeStream.Open($prototypeAudioPath, 3, $false)
  $prototypeSpeaker.AudioOutputStream = $prototypeStream
  $prototypeSpeaker.Rate = 1
  [void]$prototypeSpeaker.Speak('A pause before the evening rush. Set a place for yourself. The small moments make the story. A table worth coming back to.')
} finally {
  $prototypeStream.Close()
  [void][Runtime.InteropServices.Marshal]::ReleaseComObject($prototypeSpeaker)
  [void][Runtime.InteropServices.Marshal]::ReleaseComObject($prototypeStream)
}
