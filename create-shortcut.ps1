# 백수톡 스튜디오 — 바탕화면 바로가기 만들기
# 바탕화면 바로가기 만들기.bat 이 이 파일을 실행합니다.
# (이 파일은 UTF-8 BOM 으로 저장되어야 Windows PowerShell 에서 한글이 깨지지 않습니다)

$ErrorActionPreference = 'Stop'
$base = Split-Path -Parent $MyInvocation.MyCommand.Path

$exe = Join-Path $base '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $exe)) { $exe = Join-Path $base '.venv\Scripts\python.exe' }
if (-not (Test-Path $exe)) { $exe = 'pythonw.exe' }

$desktop = [Environment]::GetFolderPath('Desktop')
$lnkPath = Join-Path $desktop '백수톡 스튜디오.lnk'

$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($lnkPath)
$sc.TargetPath = $exe
$sc.Arguments = '"' + (Join-Path $base 'launcher.py') + '"'
$sc.WorkingDirectory = $base
$icon = Join-Path $base 'assets\app.ico'
if (Test-Path $icon) { $sc.IconLocation = $icon + ',0' }
$sc.Description = '백수톡 스튜디오 — TTS · 쇼츠 · 쿠파스 · 컷편집'
$sc.WindowStyle = 1
$sc.Save()

Write-Host ''
Write-Host "바탕화면에 '백수톡 스튜디오' 바로가기를 만들었습니다." -ForegroundColor Green
Write-Host '  대상: ' -NoNewline; Write-Host $exe
Write-Host '  폴더: ' -NoNewline; Write-Host $base
Write-Host ''
