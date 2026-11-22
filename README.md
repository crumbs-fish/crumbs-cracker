# crumbs — 跨平台压缩包密码破解驱动（zip / 7z / rar）

一个**跨平台（Linux / Windows 同一份源码）**的命令行工具：识别压缩包格式、提取可破解的哈希、
调用成熟开源引擎（**hashcat** 或 **john-jumbo**）做多线程/GPU 暴力破解，最后用原生解压工具
复核命中的明文，避免假阳性。

> 仅用于你自有或已获授权的压缩包（密码恢复、取证）。破解他人数据可能违法。

## 为什么不自己写 KDF

zip(AES) / 7z / rar5 的密钥派生分别是 PBKDF2-SHA1、SHA-256 迭代、PBKDF2-SHA256，
rar4 是自定义 SHA-1 迭代。自己实现既慢（没有 SIMD/GPU 内核）又容易出错。
本项目复用的是业界验证过的引擎：

| 格式 | 哈希签名 | john 格式 | hashcat 模式 |
|---|---|---|---|
| zip ZipCrypto（传统） | `$pkzip$` / `$pkzip2$` | PKZIP | 17200 / 17210 / 17220 / 17225（legacy 映射未验证，见"局限"） |
| zip AES-256 (WinZip) | `$zip2$` | ZIP | 13600 |
| 7z（含加密文件名） | `$7z$` | 7z | 11600 |
| rar4 | `$RAR3$` | rar | 12500 |
| rar5 | `$rar5$` | RAR5 | 13000 |

## 组成

    crumbs_cracker.py            单文件驱动，只依赖 Python 3 标准库（无第三方包）
    crumbs-cracker.sh / crumbs-cracker.bat   Linux / Windows 启动器
    engines/             引擎目录（john-jumbo 构建产物、engines.json 配置）
    scripts/win-bootstrap.ps1  Windows 一键引导（PowerShell 5.1，幂等，-DryRun 可预演）
    docs/USAGE.md        详细用法
    tests/               桩测试与样本生成

**多线程**：由引擎负责。john 用 OpenMP 吃满所有 CPU 核心（本机 2 核实测
`Will run 2 OpenMP threads`）；hashcat 在 GPU 上用数千个着色器核心。
驱动本身不复制线程池——重复实现只会和引擎抢 CPU。

## 快速开始

    # 看一眼会做什么（识别格式、给出哈希、选引擎、打印将要执行的命令）
    python3 crumbs_cracker.py check  secret.zip
    python3 crumbs_cracker.py check  secret.zip --json

    # 字典攻击
    python3 crumbs_cracker.py crack secret.zip -a wordlist -w words.txt

    # 掩码攻击（4 位数字）
    python3 crumbs_cracker.py crack secret.zip -a mask -m "?d?d?d?d"

    # 字典 + 掩码混合（words.txt 中每个词后接 2 位数字）
    python3 crumbs_cracker.py crack secret.zip -a hybrid -w words.txt -m "?d?d"

    # 只打印命令，不执行
    python3 crumbs_cracker.py crack secret.zip -a wordlist -w words.txt --dry-run

Windows 用 `crumbs-cracker.bat` 替代 `python3 crumbs_cracker.py`。

## 引擎配置（engines/engines.json）

驱动不猜路径，全部从 `engines/engines.json` 读；缺失项回退 PATH 查找：

    john_bin / john_run_dir      john 可执行文件与它的 run/ 目录
    hashcat_bin / zip2john / rar2john / sevenz2john
    unrar_bin / rar_bin / sevenz_bin / perl_bin
    gpu_available                引导脚本探测结果；false 时 auto 选 john(CPU)
    gpu_devices                  GPU 型号列表

## 引擎选择（--engine auto | hashcat | john）

- `auto`：有可用 GPU → hashcat；否则 john（CPU）。hashcat 运行期若报内存/OpenCL 致命错误，
  自动改用 john 重跑一次（只有 auto 会回退，强制 hashcat 时不会）。
- `hashcat` / `john`：强制指定，失败即报错。

## 安装

### Linux

    # 引擎与复核工具（Debian/Ubuntu）
    sudo apt install hashcat unrar p7zip-full john
    # 想用最新 bleeding-jumbo 的 john（本项目实测所用）：
    git clone --depth 1 https://github.com/openwall/john.git
    cd john/src && ./configure && make -j$(nproc) && make -s ../run/john ../run/zip2john ../run/rar2john

> 注意：只构建 `zip2john` 目标会因缺 `x86-64.o simd-intrinsics.o` 链接失败（Makefile:202-203
> 只在 default 目标里追加它们）。把 `../run/john` 一起作为目标即可。

`7z2john.pl` 需要 Perl 的 `Compress::Raw::Lzma`。无 root 时可把 deb 解到本地：

    apt-get download libcompress-raw-lzma-perl && dpkg-deb -x libcompress-raw-lzma-perl_*.deb ./perl5
    PERL5LIB=./perl5/usr/lib/x86_64-linux-gnu/perl5/5.36 perl 7z2john.pl secret.7z

### Windows

    powershell -ExecutionPolicy Bypass -File scripts\win-bootstrap.ps1 -DryRun   # 预演
    powershell -ExecutionPolicy Bypass -File scripts\win-bootstrap.ps1           # 真装

脚本装 7-Zip、hashcat、john-jumbo win64、Strawberry Perl、Python 3.12，并生成 engines.json。
Windows 上的网络注意事项（实测）：github.com 直连不通，需 gh-proxy；python.org 直链会停摆，
改用清华镜像；rarlab 需要带 `User-Agent`；系统自带 `tar.exe`(bsdtar) **不能**解 hashcat 的 .7z。

## 实测结果（本机 Debian 12，2 核 CPU，无 GPU）

| 样本 | 格式 | 提取器 | 引擎 | 结果 |
|---|---|---|---|---|
| zipcrypto.zip 183 B | zip ZipCrypto | zip2john | john PKZIP | 0.19 s 破出 secret |
| zipaes.zip 221 B | zip AES-256 | zip2john | john ZIP | 0.58 s |
| multi.zip 342 B | zip 双文件 | zip2john | john PKZIP | 0.14 s |
| sevenz.7z 222 B | 7z（加密文件名） | 7z2john.pl | john 7z | 0.12 s |
| plain7z.7z 170 B | 7z | 7z2john.pl | john 7z | 0.12 s |
| rar4.rar 113 B | rar4 | rar2john | john rar | 15.9 s |
| rar5.rar 156 B | rar5 | rar2john | john RAR5 | 1.4 s |

rar4 明显更慢：RAR3 的 KDF 是 262144 轮 SHA-1，CPU 上天然吃亏；GPU 上差距会缩小。

## GPU 实测（RTX 4060 8 GB 台式机 / 驱动 565.90 / hashcat 6.2.6）

| 格式 | hashcat 模式 | 吞吐 | 对照 john CPU（2 核） |
|---|---|---|---|
| zip AES-256 | 13600 | 2930 kH/s | 54 kH/s |
| zip ZipCrypto（多文件） | 17225 | 96 亿 H/s | 17672 kH/s |
| 7z（AES-256） | 11600 | 510 kH/s | 51.8 H/s |
| rar4（RAR3-p） | 23800 | 30.7 kH/s | 135 H/s |
| rar5 | 13000 | 48.2 kH/s | 837 H/s |

- 吞吐取自 `hashcat -b --machine-readable`。真实破解只喂几条候选时 hashcat 报的 `Speed`
  是启动开销（实测 13 H/s），不是吞吐，不能拿它判断快慢。
- 5 格式 × {正确词表, 反例词表} 真机全过：全部 `已找到密码: secret` / `未找到密码`，
  每条 6.4–7.5 秒（含进程启动、哈希提取、复核）。
- rar4 在 GPU 上比 CPU 快约 227 倍（30681 vs 135 H/s）。早期版本曾因误读那行 13 H/s
  让 auto 对 rar4 退回 john，该规则已撤销。
- 便携包自带裁剪版 hashcat（只留压缩包族 12 个 module + OpenCL 内核），包内
  `hashcat.exe -I` 能正确识别 RTX 4060；Linux 包内是 `hashcat.bin`。
驱动级验收（同一批样本，走 `crumbs_cracker.py` 全链路：识别 → 提取哈希 → 选引擎 → 破解 → 复核）：
**7 个档案 × 3 项断言 = 21/21 通过**（`check` 可解析、正确密码 `found=true`、错误密码 `found=false`），
覆盖 zip ZipCrypto、zip AES-256、多文件 zip、7z（含加密文件名）、7z 不加密头、rar4、rar5。
另外三种攻击模式实测：wordlist、mask（4 位数字 0.28 s 破出）、hybrid（词表 + 2 位数字 0.27 s 破出）。
hybrid 在 john 上走 `--stdin --mask=?w<mask>`，词表以**文件句柄**喂入而非读进内存：
201 MB / 1920 万行的词表实测，驱动常驻内存 15 MB、john 峰值 51 MB。

## 局限与已知风险

1. **hashcat 只在有 GPU 时才有意义**。无独显/无驱动时 hashcat 退化成 OpenCL CPU，
   本机 pocl 只给 256 MB 单块，任何模式都 `Not enough allocatable device memory`；
   此时 auto 自动回落 john（已实测），强制 `--engine hashcat` 会明确报错。
   GPU 路径已在 RTX 4060 台式机上逐格式验证（见上一节）。
2. **legacy `$pkzip$` 先试 GPU**。上游 zip2john 对部分包输出 `$pkzip$`（不是 `$pkzip2$`），
   auto 现在先让 hashcat 在 17200/17210/17220/17225 里试；若 hashcat 报 `No hashes loaded`
   等结构性错误，自动改用 john 重跑并打警告。`$pkzip2$`（多文件 zip）走 17220/17225，已实测能破出。
3. **7z 加密文件名（-mhe=on）需要 7z2john 解析头部**，依赖 Perl 的 Compress::Raw::Lzma；
   Windows 由 Strawberry Perl 提供，Linux 需按上面的办法 vendor。
4. **复核工具必须齐全**：命中后用 7z/unrar/rar 复核，缺少复核工具会直接报错（exit 2），
   而不是把正确密码误判成 NOT FOUND。
5. Windows 一键脚本里的 john-jumbo win64 包从 openwall 下载约 8 KB/s（15 MB 要约 30 分钟），
   脚本未设超时，请预留时间。

## 退出码

    0  找到密码（或 check 成功）
    1  未找到
    2  环境/参数错误（缺工具、格式不支持、引擎报错）
## 分发产物

| 平台 | 文件 | 说明 |
| --- | --- | --- |
| Linux x64 | `crumbs-cracker-portable-linux-x64-20261122.7z` | 约 9.8 MB，LZMA2 `-mx=7`，解压即用（`scripts/build-portable.sh` 生成） |
| Windows x64 | `crumbs-cracker-portable-win64-sfx-20261122.exe` | 约 34.4 MB，7-Zip 自解压单文件，双击即解压（`scripts/build-sfx-win.sh` 生成） |

校验值以 `releases/SHA256SUMS`（或交付目录里的同名 `.sha256`）为准——包会重打，哈希写在 README 里必然过期。

Linux 包为 LZMA2 `-mx=7`（`scripts/build-portable.sh` 生成）；Windows 包为 7-Zip 自解压单文件
`-mx=9 -m0=lzma2:d=64m:fb=273 -mmt=2`（`scripts/build-sfx-win.sh` 生成）。

Windows 用 SFX 而不是 `.7z`：Win10 资源管理器不认 `.7z`，用户得先装 7-Zip，而 7-Zip 本身就在包里，
先有鸡后有蛋。自解压 exe 双击即可解开，同样的内容比 `.7z` 还小 1.2 MB（`-mx=9` vs `-mx=7`）。
代价是老一些的杀软会对自解压 exe 报「未知的自解压程序」，加信任即可。
Linux 侧不用 SFX：`7z`/`7zz` 在发行版里随手可得，`.7z` 更透明。

两包的分发版都放在 `/home/coulddisk/压缩包爆破/`（同名 `.sha256` 校验）。

## 复用的项目与致谢

本项目的破解能力全部来自这些开源项目——我们只写驱动（识别、提取、调度、复核），没有实现任何密钥派生：

| 项目 | 版本 | 许可证 | 我们用它的什么 |
| --- | --- | --- | --- |
| [John the Ripper jumbo](https://github.com/openwall/john) | 1.9.0-jumbo-1+bleeding-37bebbe4b64 | GPL-2.0-or-later | `zip2john` / `rar2john` 提取哈希；CPU 引擎（PKZIP / ZIP / 7z / rar / RAR5）；`--mask`、`--stdin`、`-1=` 自定义字符集 |
| [hashcat](https://github.com/hashcat/hashcat) | 6.2.6（Windows 为 6.2.6 官方压缩包） | MIT | GPU 引擎；`--identify` 自动判模式；`-m 13600/11600/13000/23800/17200-17230`；`$HEX[]` 出码、potfile 隔离、`-b` 基准 |
| [7-Zip](https://www.7-zip.org/) | 23.01（`7zz` / `7z.exe`）+ `7z2hashcat` | LGPL-2.1-or-later（含 unRAR 限制条款） | 解包与密码复核；`-mhe=on` 的 7z 提取辅助；自解压模块 `7zCon.sfx`；Linux 包里的静态 `7zz` |
| [UnRAR](https://www.rarlab.com/rar_add.htm) | 6.x（`unrar`） | UnRAR 免费许可（禁止用于重建 RAR 压缩算法） | `rar` 密码复核（7z 复核不了 rar 时） |
| [Perl](https://www.perl.org/) `Compress::Raw::Lzma` | 5.x | Perl 5 license（Artistic-1.0 / GPL-1.0-or-later） | Linux 包里 vendor 的 `.so`，只给 `7z2john.pl` 解析 7z 用 |
| [Python](https://www.python.org/) | 3.8+（Windows 包内置 3.11 embeddable） | PSF-2.0 | 驱动运行时，仅标准库 |

谢谢上面所有作者和维护者：没有 john-jumbo 的格式覆盖、hashcat 的 GPU 内核、7-Zip 的稳定解包，
这个驱动只会是一个漂亮的命令行壳子。也感谢 [Openwall](https://www.openwall.com/) 与 [hashcat 团队](https://hashcat.net/)
长期维护这些工具，并允许在保留各自许可证的前提下再分发。

随包二进制的许可证原文与分发义务见 [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)。
## 许可证

- 驱动代码（`crumbs_cracker.py`、`scripts/`、`tests/`、`docs/`）：**GPL-2.0-or-later**，全文见 [LICENSE](LICENSE)。
- 随包引擎（john / hashcat / 7-Zip / unrar / Python）：各自原许可，逐条见 [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)。
- 打包分发时请一并带上 `LICENSE` 与 `THIRD_PARTY_LICENSES.md`；第三方二进制保持未修改。

## AI 生成声明

本项目代码、文档与打包脚本**全部由 AI 生成**，人类只提出需求与验收：

| 角色 | 模型 | 区间 |
| --- | --- | --- |
| 主模型（设计 / 实现 / 测试 / 文档） | DeepSeek-V4-Pro | 2026-11-10 ～ 2026-11-22 |
| 协作模型（子代理：构建、核对、文档） | DeepSeek-V4-Flash | 2026-11-10 ～ 2026-11-22 |

细节见 [AI_DISCLOSURE.md](AI_DISCLOSURE.md)。代码按 GPL-2.0-or-later 提供，**不含任何担保**。

## 合法使用

仅用于自有或已获授权的压缩包（忘记密码、取证、教学）。未经授权破解他人数据在许多司法辖区违法，
使用者自行承担全部责任。
