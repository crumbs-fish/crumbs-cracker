<#
  win-bootstrap.ps1 — Windows 破解引擎无人值守安装（可重放）
  兼容 PowerShell 5.1；文件编码 UTF-8 带 BOM（PowerShell 5.1 解析中文注释必需）。

  用法:
    powershell -NoProfile -ExecutionPolicy Bypass -File win-bootstrap.ps1 [-DryRun] [-Prefix C:\crumbs]

  说明:
    - -DryRun: 只打印将要执行的动作，不下载、不安装、不写任何文件。
    - -Prefix: 安装根目录，默认 C:\crumbs。
    - 下载一律 curl.exe -L --retry 3；解压 .zip 用系统 tar.exe；
      hashcat 的 .7z 用 7z.exe（本机 bsdtar 3.8.4 无 LZMA 支持，
      实测报 "LZMA codec is unsupported"，故 7-Zip 在第一步安装）。
    - 全部静默安装：/S、/quiet、msiexec /qn；不弹任何 UI。
    - 每步写 $Prefix\setup.log（时间戳+动作+结果）。
    - 完成后生成 $Prefix\engines\engines.json 与 $Prefix\engines\ENV.md。
#>
[CmdletBinding()]
param(
  [switch]$DryRun,
  [string]$Prefix = 'C:\crumbs'
)

$ErrorActionPreference = 'Continue'
$LogFile = Join-Path $Prefix 'setup.log'
$EngDir  = Join-Path $Prefix 'engines'
$LogsDir = Join-Path $Prefix 'logs'

# 组件固定路径（全部 Windows 绝对路径）
$sevenzBin  = 'C:\Program Files\7-Zip\7z.exe'
$rarBin     = 'C:\Program Files\WinRAR\Rar.exe'
$unrarBin   = 'C:\Program Files\WinRAR\UnRAR.exe'
$pythonBin  = 'C:\Program Files\Python312\python.exe'
$perlBin    = 'C:\Strawberry\perl\bin\perl.exe'
$hashcatDir = Join-Path $EngDir 'hashcat'
$hashcatBin = Join-Path $hashcatDir 'hashcat.exe'
$johnDir    = Join-Path $EngDir 'john'
$johnRunDir = Join-Path $johnDir 'run'
$johnBin    = Join-Path $johnRunDir 'john.exe'
$zip2john   = Join-Path $johnRunDir 'zip2john.exe'
$rar2john   = Join-Path $johnRunDir 'rar2john.exe'
$sevenz2john= Join-Path $johnRunDir '7z2john.pl'

function Write-Step {
  param([string]$Msg, [string]$Result = 'OK')
  $line = '{0:yyyy-MM-dd HH:mm:ss}  {1}  {2}' -f (Get-Date), $Msg, $Result
  if ($DryRun) { Write-Host "[DRY] $Msg" }
  else { Add-Content -Path $LogFile -Value $line -Encoding UTF8; Write-Host $line }
}

function Download {
  param([string]$Url, [string]$Out)
  if ($DryRun) { Write-Host "[DRY] C:\Windows\System32\curl.exe -L --retry 3 -o $Out $Url"; return $true }
  & 'C:\Windows\System32\curl.exe' -L --retry 3 -sS -A 'Mozilla/5.0' -o $Out $Url
  if ($LASTEXITCODE -eq 0 -and (Test-Path $Out) -and (Get-Item $Out).Length -gt 0) { return $true }
  return $false
}

function Install-Exe {
  param([string]$Exe, [string[]]$Args)
  if ($DryRun) { Write-Host "[DRY] Start-Process $Exe -ArgumentList '$($Args -join ' ')' -Wait"; return }
  Start-Process -FilePath $Exe -ArgumentList $Args -Wait
}

function Install-Msi {
  param([string]$Msi)
  if ($DryRun) { Write-Host "[DRY] C:\Windows\System32\msiexec.exe /i '$Msi' /qn /norestart"; return }
  Start-Process -FilePath 'C:\Windows\System32\msiexec.exe' -ArgumentList @('/i', $Msi, '/qn', '/norestart') -Wait
}

function Extract-Flat {
  param([string]$Archive, [string]$DestDir, [string]$Tool)
  # 解压到 DestDir，并把内层第一级目录的内容上移（这些归档通常带一层版本目录）
  if ($DryRun) { Write-Host "[DRY] extract $Archive -> $DestDir (tool=$Tool)"; return }
  New-Item -ItemType Directory -Force -Path $DestDir | Out-Null
  if ($Tool -eq '7z') { & $sevenzBin x $Archive "-o$DestDir" -y | Out-Null }
  else { & 'C:\Windows\System32\tar.exe' -xf $Archive -C $DestDir 2>$null }
  $inner = Get-ChildItem -Path $DestDir -Directory | Select-Object -First 1
  if ($inner) {
    Get-ChildItem -Path $inner.FullName -Force | ForEach-Object { Move-Item -Path $_.FullName -Destination $DestDir -Force }
    Remove-Item -Path $inner.FullName -Recurse -Force
  }
}

# ---- 0. 目录准备 ----
foreach ($d in @($Prefix, $EngDir, (Join-Path $Prefix 'tools'), (Join-Path $Prefix 'tests'), $LogsDir)) {
  if ($DryRun) { Write-Host "[DRY] New-Item -ItemType Directory -Force $d" }
  elseif (-not (Test-Path $d)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
}
Write-Step '目录准备' 'OK'

# ---- 1. 7-Zip 23.01（必须先装：hashcat.7z 要用 7z.exe 解）----
$url7z = 'https://www.7-zip.org/a/7z2301-x64.exe'   # 7-Zip 23.01 x64，实测下载成功 1,589,510 字节
$f7z = Join-Path $Prefix '7z2301-x64.exe'
if (-not $DryRun -and (Test-Path $sevenzBin)) { Write-Step '7-Zip 已存在，跳过' 'OK' }
else {
  if (Download $url7z $f7z) {
    Install-Exe $f7z @('/S')
    if ($DryRun -or (Test-Path $sevenzBin)) { Write-Step '7-Zip 23.01 安装' 'OK' } else { Write-Step '7-Zip 安装' 'FAIL' }
  } else { Write-Step '7-Zip 下载' 'FAIL' }
}

# ---- 2. hashcat 6.2.6 ----
$urlHc = 'https://hashcat.net/files/hashcat-6.2.6.7z'  # hashcat 6.2.6，实测下载成功 20,951,515 字节
$fHc = Join-Path $Prefix 'hashcat.7z'
if (-not $DryRun -and (Test-Path $hashcatBin)) { Write-Step 'hashcat 已存在，跳过' 'OK' }
else {
  if (Download $urlHc $fHc) {
    Extract-Flat $fHc $hashcatDir '7z'   # bsdtar 3.8.4 不支持 LZMA，必须用 7z.exe
    if ($DryRun -or (Test-Path $hashcatBin)) { Write-Step 'hashcat 6.2.6 解压' 'OK' } else { Write-Step 'hashcat 解压' 'FAIL' }
  } else { Write-Step 'hashcat 下载' 'FAIL' }
}

# ---- 3. hashcat 自检与 GPU 探测 ----
$gpuAvailable = $false
$gpuDevices = @()
if ($DryRun) {
  Write-Host "[DRY] $hashcatBin --version"
  Write-Host "[DRY] $hashcatBin -I > $LogsDir\hashcat-I.txt"
} elseif (Test-Path $hashcatBin) {
  $hcVer = (& $hashcatBin --version 2>&1 | Select-Object -First 1)
  Write-Step 'hashcat --version' ("v=$hcVer")
  $hcI = & $hashcatBin -I 2>&1 | Out-String
  $hcI | Set-Content -Path (Join-Path $LogsDir 'hashcat-I.txt') -Encoding UTF8
  if ($hcI -match 'Type[\.\s]*:?\s*GPU' -and $hcI -match 'GTX 1650') {
    $gpuAvailable = $true
    $gpuDevices = @('NVIDIA GeForce GTX 1650')
  }
  Write-Step 'hashcat -I' ("gpu_available=$gpuAvailable")
} else { Write-Step 'hashcat 自检' 'SKIP(未安装)' }

# ---- 4. WinRAR ----
# rarlab 下载页当前英文 x64 直链；curl 需 -A 浏览器 UA（否则 schannel close_notify）
$urlRar = 'https://www.rarlab.com/rar/winrar-x64-730b2.exe'  # WinRAR 7.30 beta 2 x64，实测下载成功 3,790,728 字节
$fRar = Join-Path $Prefix 'winrar-x64-730b2.exe'
if (-not $DryRun -and (Test-Path $rarBin) -and (Test-Path $unrarBin)) { Write-Step 'WinRAR 已存在，跳过' 'OK' }
else {
  if (Download $urlRar $fRar) {
    Install-Exe $fRar @('/S')
    if ($DryRun -or ((Test-Path $rarBin) -and (Test-Path $unrarBin))) { Write-Step 'WinRAR 安装' 'OK' } else { Write-Step 'WinRAR 安装' 'FAIL' }
  } else { Write-Step 'WinRAR 下载' 'FAIL' }
}

# ---- 5. Python 3.12.10 ----
# python.org 直链在本机实测停摆（0 字节），改用清华镜像（实测 200/206 可达，约 1.6MB/s）
$urlPy = 'https://mirrors.tuna.tsinghua.edu.cn/python/3.12.10/python-3.12.10-amd64.exe'
$fPy = Join-Path $Prefix 'python-3.12.10-amd64.exe'
if (-not $DryRun -and (Test-Path $pythonBin)) { Write-Step 'Python 已存在，跳过' 'OK' }
else {
  if (Download $urlPy $fPy) {
    Install-Exe $fPy @('/quiet', 'InstallAllUsers=1', 'PrependPath=1', 'Include_launcher=1', 'Include_test=0')
    if ($DryRun -or (Test-Path $pythonBin)) { Write-Step 'Python 3.12.10 安装' 'OK' } else { Write-Step 'Python 安装' 'FAIL' }
  } else { Write-Step 'Python 下载' 'FAIL' }
}

# ---- 6. john-jumbo 1.9.0 win64 ----
$urlJohn = 'https://www.openwall.com/john/k/john-1.9.0-jumbo-1-win64.zip'  # 页面核实 200；本机实测约 8KB/s，较慢
$fJohn = Join-Path $Prefix 'john-1.9.0-jumbo-1-win64.zip'
if (-not $DryRun -and (Test-Path $johnBin)) { Write-Step 'john 已存在，跳过' 'OK' }
else {
  if (Download $urlJohn $fJohn) {
    Extract-Flat $fJohn $johnDir 'tar'   # .zip 用 tar.exe（bsdtar 支持 zip）
    if ($DryRun -or (Test-Path $johnBin)) { Write-Step 'john-jumbo 解压' 'OK' } else { Write-Step 'john 解压' 'FAIL' }
    if (-not $DryRun -and (Test-Path $johnBin)) {
      $fmt = & $johnBin '--list=formats' 2>&1 | Out-String
      if ($fmt -match 'zip' -and $fmt -match 'rar') { Write-Step 'john --list=formats' 'zip+rar OK' } else { Write-Step 'john --list=formats' 'FAIL' }
    }
  } else { Write-Step 'john 下载' 'FAIL' }
}

# ---- 7. Strawberry Perl 5.40.5.1 ----
# github.com 在本机被墙；用 gh-proxy.com 反代（实测 200，Content-Length 209,716,197）
$urlPerl = 'https://gh-proxy.com/https://github.com/StrawberryPerl/Perl-Dist-Strawberry/releases/download/SP_54051_64bit/strawberry-perl-5.40.5.1-64bit.msi'
$fPerl = Join-Path $Prefix 'strawberry-perl-5.40.5.1-64bit.msi'
if (-not $DryRun -and (Test-Path $perlBin)) { Write-Step 'Strawberry Perl 已存在，跳过' 'OK' }
else {
  if (Download $urlPerl $fPerl) {
    Install-Msi $fPerl
    if ($DryRun -or (Test-Path $perlBin)) { Write-Step 'Strawberry Perl 5.40.5.1 安装' 'OK' } else { Write-Step 'Strawberry Perl 安装' 'FAIL' }
  } else { Write-Step 'Strawberry Perl 下载' 'FAIL' }
}

# ---- 8. perl 运行 7z2john.pl 用法检查 ----
if ($DryRun) {
  Write-Host "[DRY] $perlBin $sevenz2john"
} elseif ((Test-Path $perlBin) -and (Test-Path $sevenz2john)) {
  $p = & $perlBin $sevenz2john 2>&1 | Out-String
  if ($p -match 'Usage|usage|用法') { Write-Step '7z2john.pl 用法检查' 'OK' } else { Write-Step '7z2john.pl 用法检查' 'FAIL' }
} else { Write-Step '7z2john.pl 用法检查' 'SKIP(缺 perl 或脚本)' }

# ---- 9. engines.json ----
$jsonPath = Join-Path $EngDir 'engines.json'
$notes = "win-bootstrap.ps1 replay. hashcat 6.2.6; 7-Zip 23.01; WinRAR 7.30b2; Python 3.12.10; Strawberry Perl 5.40.5.1; john 1.9.0-jumbo-1-win64. gpu_available=$gpuAvailable"
$engine = [ordered]@{
  john_run_dir  = $johnRunDir
  john_bin      = $johnBin
  hashcat_bin   = $hashcatBin
  zip2john      = $zip2john
  rar2john      = $rar2john
  sevenz2john   = $sevenz2john
  unrar_bin     = $unrarBin
  rar_bin       = $rarBin
  sevenz_bin    = $sevenzBin
  python_bin    = $pythonBin
  perl_bin      = $perlBin
  gpu_available = $gpuAvailable
  gpu_devices   = $gpuDevices
  notes         = $notes
}
$json = $engine | ConvertTo-Json -Depth 3
if ($DryRun) {
  Write-Host "[DRY] write engines.json -> $jsonPath"
  Write-Host "[DRY] json preview: $json"
} else {
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($jsonPath, $json, $utf8NoBom)
  Write-Step 'engines.json 写入' 'OK'
  if (Test-Path $pythonBin) {
    $code = "import json;print(json.load(open(r'$jsonPath'))['gpu_available'])"
    $chk = & $pythonBin -c $code 2>&1 | Out-String
    Write-Step 'engines.json python 校验' ("gpu_available=$chk")
  }
}

# ---- 10. ENV.md ----
$envMd = Join-Path $EngDir 'ENV.md'
if (-not $DryRun) {
  $md = @"
# Windows 破解引擎环境（win-bootstrap.ps1 重放结果）

- 根目录: $Prefix
- hashcat: 6.2.6 -> $hashcatBin
- 7-Zip: 23.01 -> $sevenzBin
- WinRAR: 7.30 beta 2 -> $rarBin / $unrarBin
- Python: 3.12.10 -> $pythonBin
- Strawberry Perl: 5.40.5.1 -> $perlBin
- john-jumbo: 1.9.0-jumbo-1-win64 -> $johnRunDir
- GPU: available=$gpuAvailable devices=$($gpuDevices -join ',')
- hashcat -I 摘要: $LogsDir\hashcat-I.txt
- 安装日志: $LogFile
"@
  [System.IO.File]::WriteAllText($envMd, $md, $utf8NoBom)
  Write-Step 'ENV.md 写入' 'OK'
}

# ---- 11. 清理安装包 ----
if (-not $DryRun) {
  Get-ChildItem $Prefix -File | Where-Object { $_.Extension -in @('.7z','.zip','.exe','.msi') } | Remove-Item -Force
  Write-Step '安装包清理' 'OK'
}

Write-Step 'win-bootstrap 完成' 'DONE'
