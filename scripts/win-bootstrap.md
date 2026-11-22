# win-bootstrap 使用说明

Windows 破解引擎无人值守重放脚本。目标机：Windows 10 19045 / NVIDIA GTX 1650 4GB / 驱动 581.94 / Administrator。

## 从 Linux 连 Windows（可复用配方）

~~~bash
cat > /tmp/win_askpass.sh <<'EOF'
#!/bin/sh
printf '%s\n' '1'
EOF
chmod +x /tmp/win_askpass.sh
export SSH_ASKPASS=/tmp/win_askpass.sh SSH_ASKPASS_REQUIRE=force DISPLAY=:0
SSH="setsid -w ssh -p 2222 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR Administrator@127.0.0.1"
SCP="setsid -w scp -P 2222 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR"
$SSH "echo CONNECT_OK & ver"
~~~

## 重放步骤

~~~bash
source /tmp/win_conn.sh   # 或重新 export 上面的变量
$SCP scripts/win-bootstrap.ps1 Administrator@127.0.0.1:C:/crumbs/win-bootstrap.ps1
$SSH "powershell -NoProfile -ExecutionPolicy Bypass -File C:/crumbs/win-bootstrap.ps1 -DryRun"
$SSH "powershell -NoProfile -ExecutionPolicy Bypass -File C:/crumbs/win-bootstrap.ps1"
~~~

## 组件与 URL（均在本机实测）

| 组件 | 版本 | URL | 实测证据 | 安装/解压方式 |
|---|---|---|---|---|
| hashcat | 6.2.6 | https://hashcat.net/files/hashcat-6.2.6.7z | Windows curl 下载成功 20,951,515 B | 7z.exe 解压（tar.exe 3.8.4 无 LZMA） |
| 7-Zip | 23.01 | https://www.7-zip.org/a/7z2301-x64.exe | Windows curl 下载成功 1,589,510 B | /S |
| WinRAR | 7.30 beta2 | https://www.rarlab.com/rar/winrar-x64-730b2.exe | Windows curl 下载成功 3,790,728 B（需 -A UA） | /S |
| Python | 3.12.10 | https://mirrors.tuna.tsinghua.edu.cn/python/3.12.10/python-3.12.10-amd64.exe | 200/206 可达，约 1.6MB/s | /quiet InstallAllUsers=1 PrependPath=1 Include_launcher=1 Include_test=0 |
| john-jumbo | 1.9.0-jumbo-1-win64 | https://www.openwall.com/john/k/john-1.9.0-jumbo-1-win64.zip | 200 可达；约 8KB/s 较慢 | tar.exe 解 zip |
| Strawberry Perl | 5.40.5.1 | https://gh-proxy.com/https://github.com/StrawberryPerl/Perl-Dist-Strawberry/releases/download/SP_54051_64bit/strawberry-perl-5.40.5.1-64bit.msi | 200 可达，209,716,197 B | msiexec /i ... /qn /norestart |

## 关键实测结论（决定实现方式）

- winget 源不可用（0x8a15000f，winget source reset --force 后仍失败）→ 全部改直链下载。
- tar.exe = bsdtar 3.8.4，解 hashcat.7z 实测报 LZMA codec is unsupported → hashcat 的 .7z 必须用 7z.exe 解（脚本第 1 步先装 7-Zip）。父代理所说 bsdtar 8.3.4 可解 7z 与本机实测不符。
- github.com 从 Windows 不可达（000），但 gh-proxy.com 反代可用 → Strawberry Perl（官方仅 GitHub 分发）走 gh-proxy。
- python.org 直链从 Windows 下载停摆（0 字节）→ 改用清华镜像。
- openwall 下载慢（约 8KB/s），john zip 约 15MB 预计需约 30 分钟；脚本 curl 不设 --max-time，会一直等。
- rarlab 服务器 schannel 会 close_notify，curl 需 -A 'Mozilla/5.0'（脚本已内置）。

## engines.json schema

键：john_run_dir / john_bin / hashcat_bin / zip2john / rar2john / sevenz2john / unrar_bin / rar_bin / sevenz_bin / python_bin / perl_bin / gpu_available / gpu_devices / notes。
gpu_available 由 hashcat.exe -I 输出判断：同时出现 Type...: GPU 与 GTX 1650 才为 true。

## DryRun

-DryRun 只打印动作（curl 命令、安装命令、解压命令、将要写入的文件），不下载、不安装、不落盘。

## 还原后如果 sshd 没起来（手动开 OpenSSH 服务器）

1. 本机操作：设置 → 应用 → 可选功能 → 添加功能 → OpenSSH 服务器 → 安装。
2. 或用管理员 PowerShell：
   Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
   Start-Service sshd
   Set-Service -Name sshd -StartupType Automatic
3. 端口不通时确认监听：netstat -ano | findstr :2222

## 脚本调用方式

    powershell -NoProfile -ExecutionPolicy Bypass -File C:\crumbs\win-bootstrap.ps1 -DryRun
    powershell -NoProfile -ExecutionPolicy Bypass -File C:\crumbs\win-bootstrap.ps1
    powershell -NoProfile -ExecutionPolicy Bypass -File C:\crumbs\win-bootstrap.ps1 -Prefix D:\crumbs

## 编码说明（重要）

win-bootstrap.ps1 是 UTF-8 带 BOM：PowerShell 5.1 对无 BOM 文件按 ANSI(GBK) 解析，中文字节会吞掉后续引号，实测报 MissingEndParenthesisInExpression。父要求"UTF-8 无 BOM"与"注释用中文"在 PS 5.1 下不可兼得，取 BOM 保可运行。win-bootstrap.md 保持无 BOM。
