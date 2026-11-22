# crumbs-cracker

找回 zip、7z、rar 压缩包密码的命令行工具，Linux 和 Windows 都能用。

> 只用来找回你自己（或已获授权）的压缩包密码。拿去破解别人的数据，在很多地方是违法的。

### 特性

* 单文件 Python 驱动，只用标准库，Linux / Windows 同一份源码
* 支持 zip（ZipCrypto / AES-256）、7z（含加密文件名 `-mhe=on`）、rar4、rar5
* 有 GPU 自动交给 hashcat，没有就用 john 吃满 CPU，跑到一半挂了会自动换
* 字典、掩码、混合三种攻击方式；密码长度未知可以一位一位试
* 命中的密码会用 7-Zip / unrar 真解压复核，宁可不报也不报假的
* 什么都不带直接运行会进中文问答向导，一步步问你要怎么破
* 便携包开箱即用，Windows 版连 Python 都内置

### 支持的格式

| 格式 | 哈希签名 | CPU（john） | GPU（hashcat） |
| --- | --- | --- | --- |
| zip ZipCrypto | `$pkzip$` / `$pkzip2$` | PKZIP | 17200–17225 |
| zip AES-256 (WinZip) | `$zip2$` | ZIP | 13600 |
| 7z（含加密文件名） | `$7z$` | 7z | 11600 |
| rar4 | `$RAR3$` | rar | 12500 / 23800 |
| rar5 | `$rar5$` | RAR5 | 13000 |

### 许可证

驱动代码（`crumbs_cracker.py`、`scripts/`、`tests/`、`docs/`）采用 **GPL-2.0-or-later**，全文见
[LICENSE](LICENSE)。随包引擎（john / hashcat / 7-Zip / unrar / Python）保持各自原许可，逐条见
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)。

### 使用

到 [Releases](https://github.com/crumbs-fish/crumbs-cracker/releases) 页下载对应平台的便携包：

| 平台 | 文件 | 打开方式 |
| --- | --- | --- |
| Linux x64 | `crumbs-cracker-portable-linux-x64-YYYYMMDD.7z` | `7z x` 解压 |
| Windows x64 | `crumbs-cracker-portable-win64-sfx-YYYYMMDD.exe` | 双击自解压 |

Windows 版把 Python 都内置了，所以做成自解压 exe（资源管理器默认不认 .7z）；老杀软偶尔会报
未知自解压程序，加信任即可。解压后进目录，Linux 用 `./crumbs-cracker.sh`，Windows 用
`crumbs-cracker.bat`，后面接同样的命令。

先看包的情况（格式、哈希、选哪个引擎、要跑什么命令）：

```bash
./crumbs-cracker.sh check secret.zip
./crumbs-cracker.sh check secret.zip --json
```

三种攻击方式：

```bash
# 字典：words.txt 里逐行放候选密码
./crumbs-cracker.sh crack secret.zip -a wordlist -w words.txt

# 掩码：比如 4 位纯数字
./crumbs-cracker.sh crack secret.zip -a mask -m "?d?d?d?d"

# 混合：每个字典词后面接 2 位数字
./crumbs-cracker.sh crack secret.zip -a hybrid -w words.txt -m "?d?d"
```

不知道密码多长就 `--len-min 1 --len-max 12`，会一位一位试过去。什么都不带直接运行，
会进中文问答向导。校验值以 `releases/SHA256SUMS` 为准。

退出码：0 找到（或 check 通过）、1 没找到、2 环境或参数有问题（缺工具、格式不支持），
写脚本可以直接按退出码判断。

### 引擎怎么选

默认 auto：先用 `hashcat -I` 探一遍，有 GPU 就用 hashcat，没有就用 john 吃满 CPU。
hashcat 跑到一半报显存不足之类，auto 会自动换 john 重跑一次。`--engine hashcat` 或
`--engine john` 可以钉死，钉死之后失败就报错，不会自己换。

### 从源码构建

```bash
git clone https://github.com/crumbs-fish/crumbs-cracker
cd crumbs-cracker
```

驱动本身零依赖，有 Python 3.8+ 就能跑；引擎和复核工具要另外装，装完写一份
`engines/engines.json` 指过去（键：`john_bin` / `hashcat_bin` / `zip2john` / `rar2john` /
`sevenz2john` / `unrar_bin` / `rar_bin` / `sevenz_bin` / `perl_bin`，找不到文件或不想写
也可以 `--engines` 指到自己的配置）。

Linux（Debian/Ubuntu）装引擎：

```bash
sudo apt install hashcat unrar p7zip-full john
```

想跟项目实测环境一致，用 bleeding-jumbo 的 john：

```bash
git clone --depth 1 https://github.com/openwall/john.git
cd john/src && ./configure && make -j$(nproc) && make -s ../run/john ../run/zip2john ../run/rar2john
```

小坑：只编译 `zip2john` 一个目标会缺 `x86-64.o`、`simd-intrinsics.o` 链接失败，
把 `../run/john` 一起带上就行。7z 连文件名一起加密（`-mhe=on`）需要 7z2john.pl，
它依赖 Perl 的 Compress::Raw::Lzma，没 root 可以解 deb 到本地：

```bash
apt-get download libcompress-raw-lzma-perl && dpkg-deb -x libcompress-raw-lzma-perl_*.deb ./perl5
PERL5LIB=./perl5/usr/lib/x86_64-linux-gnu/perl5/5.36 perl 7z2john.pl secret.7z
```

Windows：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\win-bootstrap.ps1 -DryRun
powershell -ExecutionPolicy Bypass -File scripts\win-bootstrap.ps1
```

脚本会装齐 7-Zip、hashcat、john-jumbo、Strawberry Perl、Python 3.12，并生成 engines.json。
国内网络常见情况：github.com 直连可能不通，需要代理；python.org 直链可能停摆，可以换清华镜像；
rarlab 下载要带 User-Agent；系统自带的 tar.exe（bsdtar）解不了 hashcat 的 .7z。

装完之后，用 `python3 crumbs_cracker.py` 代替上面的 `./crumbs-cracker.sh`，参数完全一样。

### 跑得有多快

下面是测试机上的参考数字，不同机器差别很大，尤其是显卡。CPU 一列是 john 的 OpenMP 全核，
GPU 一列是 hashcat `-b --machine-readable` 的吞吐：

| 格式 | CPU（john） | GPU（hashcat） |
| --- | --- | --- |
| zip ZipCrypto | 17,672 kH/s | 9,649 MH/s |
| zip AES-256 | 54 kH/s | 2,930 kH/s |
| 7z | 51.8 H/s | 510 kH/s |
| rar4 | 135 H/s | 30.7 kH/s |
| rar5 | 837 H/s | 48.2 kH/s |

两点提醒：真实破解只喂几条候选时，hashcat 状态栏里的 Speed 是启动开销，不是吞吐，别拿它判断快慢；
rar4 在 CPU 上特别慢是因为 RAR3 要滚 262144 轮 SHA-1，GPU 上差距会小很多。混合模式走
`--stdin --mask`，词表以文件句柄喂给 john 而不是读进内存，词表再大驱动自己的内存占用也基本不变。

### 已知问题

* hashcat 得有 GPU 才值得用。没有独显时它退化成 OpenCL CPU，部分实现只给一小块单块显存，
  任何模式都报 `Not enough allocatable device memory`，交给 auto 处理就好，它会回 john。
* 上游 zip2john 对部分包输出旧式 `$pkzip$` 签名，映射关系没全验证。驱动会先让 hashcat 试，
  试不动再退回 john 并打警告；常见的 `$pkzip2$` 多文件 zip 是验证过的。
* 7z 连文件名一起加密时，提取哈希必须经过 7z2john.pl 和 Perl 的 Compress::Raw::Lzma。
  Windows 包里自带 Strawberry Perl，Linux 看从源码构建一节。
* 命中的密码一定要用 7z / unrar / rar 解压复核，缺工具直接报错，宁可不报结果也不报假结果。
* Windows 引导脚本要从 openwall 下 john-jumbo（15 MB 左右），那家网速经常只有 8 KB/s，请留半小时。

### 致谢

这个工具的所有算力都来自下面这些项目：

| 项目 | 版本 | 许可证 | 用在哪 |
| --- | --- | --- | --- |
| [John the Ripper jumbo](https://github.com/openwall/john) | 1.9.0-jumbo-1+bleeding-37bebbe4b64 | GPL-2.0-or-later | zip2john / rar2john 提取；CPU 破解；`--mask`、`--stdin`、`-1=` |
| [hashcat](https://github.com/hashcat/hashcat) | 6.2.6 | MIT | GPU 破解；`--identify`；13600/11600/13000/23800/172xx；`$HEX[]` 出码 |
| [7-Zip](https://www.7-zip.org/) | 23.01（`7zz` / `7z.exe` + `7z2hashcat`） | LGPL-2.1-or-later（含 unRAR 条款） | 解包复核；`-mhe=on` 解析；自解压模块 `7zCon.sfx`；静态 `7zz` |
| [UnRAR](https://www.rarlab.com/rar_add.htm) | 6.x | UnRAR 许可（禁止用于重建 RAR 算法） | rar 密码复核 |
| Perl [Compress::Raw::Lzma](https://metacpan.org/pod/Compress::Raw::Lzma) | 5.x | Perl 5（Artistic / GPL-1.0-or-later） | Linux 包里 vendor 给 7z2john.pl 用 |
| [Python](https://www.python.org/) | 3.8+ | PSF-2.0 | 驱动运行时，只用标准库 |

谢谢 Openwall 和 hashcat 团队长期维护这些工具，也谢谢 7-Zip 和 rarlab 允许在各自许可证下再分发。
随包二进制各自的许可证原文在 [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)。

### 关于这个项目怎么来的

直说：这个仓库的代码、文档、打包脚本全部由 AI 生成（DeepSeek-V4-Pro 为主，DeepSeek-V4-Flash 干子任务），
时间是 2026-11-10 到 2026-11-22，人类做的是提需求、验收和真机测试。细节在
[AI_DISCLOSURE.md](AI_DISCLOSURE.md)。

### 合法使用

只用于找回你自己的密码。未经授权破解他人数据，责任自负。
