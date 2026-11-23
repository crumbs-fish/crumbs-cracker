# arm64 上怎么用

crumbs-cracker 的驱动是纯 Python 标准库，arm64 上跟 x64 是同一份代码。
麻烦的是引擎：x64 的便携包里直接塞了编译好的 john 和 hashcat，arm64 没有，
得在机器上装一遍。仓库里有两个脚本干这件事。

两种情况：

| 设备 | 脚本 | 引擎来源 | 大约耗时 |
| --- | --- | --- | --- |
| 安卓手机 / 平板（Termux） | `scripts/build-termux.sh` | john 本地编译，7zip / unrar / perl 用 pkg 装 | 10-30 分钟 |
| arm64 Linux（Switch 上的 switchroot Ubuntu、树莓派一类） | `scripts/build-switchroot.sh` | 全部 apt 装，不编译 | 1-3 分钟 |

两边都只有 CPU 引擎（john）。理由写在最后。

## Android（Termux）

先在应用商店装 Termux（用 F-Droid 或 GitHub 的版本，Play 商店那个太旧），然后：

```bash
pkg install git
git clone https://github.com/crumbs-fish/crumbs-cracker
cd crumbs-cracker
bash scripts/build-termux.sh
```

脚本会依次做这些事：

1. `pkg install` 装 python / clang / make / perl / 7zip / unrar / git / openssl / liblzma；
2. 按固定 commit 拉 john-jumbo 源码到 `~/.cache/crumbs-john`；
3. `./configure --disable-native-tests` 加 `make -j`（并发上限 6，手机上并行太多容易 OOM）；
4. 把 `john`、`zip2john`、`rar2john`、`7z2john.pl`、`john.conf` 拷进 `engines/john/run/`；
5. 试装 `Compress::Raw::Lzma`（7z 提取器需要，装不上只影响 7z）；
6. 生成 `engines/engines.json`（7z / unrar 用系统里的绝对路径）；
7. 造一个密码 `secret` 的 zip，跑一遍 `check` 和字典破解自检。

自检过了就能用：

```bash
python3 crumbs_cracker.py check ~/storage/downloads/我的.zip
python3 crumbs_cracker.py crack -a wordlist -w dicts/common-100k.txt ~/storage/downloads/我的.zip
```

手机上的文件要先 `termux-setup-storage` 授权，之后在 `~/storage/downloads` 之类的位置能看到。

编译中途断掉的话，直接重跑脚本，源码目录会复用。日志在 `~/.cache/crumbs-john-build.log`。

## arm64 Linux

Ubuntu / Debian 系（switchroot 用的是这套）：

```bash
sudo apt-get install -y git
git clone https://github.com/crumbs-fish/crumbs-cracker
cd crumbs-cracker
bash scripts/build-switchroot.sh
```

脚本装 `john`、`p7zip-full`、`perl`，再试 `unrar`（装不上退 `unrar-free`），
然后按 `command -v` 和 `/usr/sbin` 一类目录找齐可执行文件，把绝对路径写进
`engines/engines.json`，最后同样跑一遍自检。

apt 的 john 会把 `john`、`zip2john`、`rar2john` 放在 `/usr/sbin`，普通用户的 PATH 里常常没有
`/usr/sbin`，所以这里的配置一律写绝对路径，不需要改 PATH。

## 速度大概什么样

都是 CPU、单线程到多线程的量级，跟 x64 比大概这样：

- zip ZipCrypto：够用，弱口令字典几分钟内出结果；
- zip AES-256：很慢，只适合短密码 + 小字典；
- 7z：最慢，纯 CPU 基本只能碰运气；
- rar4 / rar5：rar5 比 rar4 快一些，但都别指望暴力枚举。

真要认真破，还是拿带独显的机器跑 hashcat。

## 为什么只有 CPU

- **Android 非 root**：厂商的 OpenCL 驱动没有暴露给普通应用，Termux 里能装的只有
  `mesa-opencl-icd-rusticl`（Mesa 的 Rust 版 OpenCL）和 `clinfo` 这类东西，
  Adreno / Mali 上要跑通 hashcat 得 root 后塞厂商的 `libOpenCL.so`，现在的脚本不做这件事。
- **arm64 Linux**：switchroot 这类移植系统没有可用的 OpenCL 运行时（Tegra X1 的 GPU 驱动
  在 Linux 侧只有 nouveau / 部分 opentegra 支持），hashcat 起不来，所以脚本直接用 john。
- 驱动本身在 GPU 探测失败时会自动退回 john，所以就算以后装上了 OpenCL，也不用改代码。

## 已知问题

- Termux 上编译 john 需要约 1.5 GB 空间，空间不够会在 `make` 阶段报错；
- 安卓的 `7z2john.pl` 依赖 `Compress::Raw::Lzma`，`cpan` 装不上时 7z 格式会提示提取失败，
  zip / rar 不受影响；
- arm64 上没有打包好的便携版，要自己 clone 源码跑脚本；
- iOS 不在支持范围内。
