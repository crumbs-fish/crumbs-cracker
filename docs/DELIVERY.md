# 交付说明（2026-11-09 夜）

## 一、交付物

    crumbs-cracker/
      crumbs_cracker.py                驱动（Python 3 标准库，Linux/Windows 同一份，~800 行）
      crumbs-cracker.sh / crumbs-cracker.bat   Linux / Windows 启动器
      README.md                总览、格式-引擎映射、安装、实测、局限
      docs/USAGE.md            子命令与参数详解
      docs/DELIVERY.md         本文件：证据、风险、明天的待办
      scripts/win-bootstrap.ps1  Windows 一键引导（PS 5.1，-DryRun/-Prefix，幂等）
      scripts/win-bootstrap.md   脚本说明与 Windows 实测坑
      engines/engines.json     引擎路径配置（本机 Linux）
      engines/john/            john-jumbo 1.9.0-jumbo-1+bleeding-37bebbe4b64（CPU 构建）
      engines/bin/7z2john      perl 包装脚本（vendor 了 Compress::Raw::Lzma）
      tests/                   桩测试 + 样本

## 二、本机（Debian 12 / 2 核 / 1 GB / 无 GPU）验收结果

驱动级：**21/21 通过**（7 个档案 × {check、正确密码、错误密码}），命令：

    bash /tmp/crumbs_accept.sh        # 我写的独立验收脚本（不属于子代理产物）

| 样本 | 提取器 | 引擎 | 复核 | 结果 |
|---|---|---|---|---|
| zipcrypto.zip（ZipCrypto） | zip2john | john PKZIP | 7z | found=secret |
| zipaes.zip（AES-256） | zip2john | john ZIP | 7z | found=secret |
| multi.zip（双文件） | zip2john | john PKZIP | 7z | found=secret |
| sevenz.7z（-mhe=on） | 7z2john.pl | john 7z | 7z | found=secret |
| plain7z.7z | 7z2john.pl | john 7z | 7z | found=secret |
| rar4.rar | rar2john | john rar | unrar | found=secret |
| rar5.rar | rar2john | john RAR5 | unrar | found=secret |

攻击模式：wordlist / mask（4 位数字 0.28 s）/ hybrid（词表+2 位数字 0.27 s）全部实测通过。
hybrid 的词表用文件句柄喂 stdin：201 MB、1920 万行词表实测驱动常驻 15 MB、john 峰值 51 MB。

退出码：找到 0、未找到 1、环境/参数错 2（实测）。

## 三、已知风险（未解决项，明天要做）

1. ~~GPU 路径未验证~~ **已于 2026-11-10 在 RTX 4060 上验证**：13600/11600/13000/23800
   四个模式真机破出 secret，5 格式 × {正例, 反例} 全过；benchmark 13600 ≈ 2930 kH/s、
   11600 ≈ 510 kH/s、13000 ≈ 48.2 kH/s、23800 ≈ 30.7 kH/s。
   无 GPU 的 Linux 上 auto 自动回落 john（已实测）。
2. **legacy `$pkzip$` 仍走 john**。上游 zip2john 已回退到 `$pkzip$`，auto 对它选 john
   并打警告；`$pkzip2$`（多文件 zip）走 hashcat 17220/17225，已实测能破出。
3. **7z2john 依赖 Perl Compress::Raw::Lzma**。Linux 用 apt 包解出的 vendor 目录（无 root），
   Windows 由 Strawberry Perl 自带；换机器要重新 vendor。
4. **Windows 脚本未在本机复跑**（机器 20:20 关机并会还原）。脚本本身在 Windows 上逐条实测过
   下载源与命令，但明天应在还原后的干净系统上从零跑一遍。
5. rar4 的样本必须用 **rar 6.0.2** 造（rar 7.01 删了 `-ma4`）。

## 四、明天的执行顺序（约 40 分钟）

1. Windows 开机后：`powershell -ExecutionPolicy Bypass -File scripts\win-bootstrap.ps1`
   （john win64 包约 8 KB/s，15 MB 需 ~30 分钟，先把这条挂上再干别的）。
2. 装完后确认 `C:\crumbs\engines\engines.json` 里 gpu_available=true、gpu_devices 含 GTX 1650。
3. 在 Windows 上造 5 个加密样本（7z.exe ZipCrypto/AES、7z、WinRAR 造 rar4/rar5 用 UnRAR 验证）。
4. 用 `crumbs-cracker.bat check/crack --json` 跑同一套断言，重点看 engine=hashcat、backend=gpu。
5. 回来把实测数字补进 README 与本文档。

## 五、收尾纪律

- 22:00 后本机零活动；未申请 root、未改系统配置、未碰用户数据与 QQ。
- 中间产物已清：`engines/perl5`（重复 vendor）、`__pycache__`、/tmp 下的抓包与临时目录。
- 磁盘：项目 179 MB，可用 1.8 GB。
