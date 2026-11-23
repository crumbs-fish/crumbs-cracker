# 第三方组件与许可

本项目的**驱动代码**（`crumbs_cracker.py`、`scripts/`、`tests/`、`docs/`）以
**GPL-2.0-or-later** 授权，全文见 `LICENSE`。

随包分发的可执行引擎不是我们的作品，各自保留原许可；它们通过**独立进程 + 命令行**调用，
按 GPLv2 第 2 节末段的“聚合”规则，不影响驱动本身的授权。

| 组件 | 版本 / 位置 | 许可 | 源码 |
| --- | --- | --- | --- |
| John the Ripper jumbo（john / zip2john / rar2john / 7z2john.pl） | 1.9.0-jumbo-1+bleeding-37bebbe4b64，`engines/john/` | GPLv2+（部分组件更宽松） | https://github.com/openwall/john |
| hashcat（仅压缩包相关模式模块） | 6.2.6，`engines/hashcat/` | MIT（内含 LZMA SDK、miniz、OpenCL headers 等，见 `licenses/hashcat-license_libs/`） | https://github.com/hashcat/hashcat |
| 7-Zip 命令行 | 23.01，`engines/bin/7zz`（Windows 包为 `bin/7z.exe`） | LGPL-2.1+ 与部分 BSD；含 unRAR 限制 | https://www.7-zip.org/ |
| UnRAR | Linux 包 6.2.4，`engines/bin/unrar` | RARLAB 免费许可（允许随包分发未修改版本，禁止用于实现 RAR 压缩） | https://www.rarlab.com/license.htm |
| Perl `Compress::Raw::Lzma` | Debian 包解包，`engines/vendor/perl5/` | Perl 5 许可（GPL-1.0+ / Artistic） | https://metacpan.org/pod/Compress::Raw::Lzma |
| Python（Windows 便携包） | 3.12 embeddable，`python/` | PSF License | https://docs.python.org/3/license.html |

## 许可证原文

随包附带的原文在 `licenses/` 目录（驱动自身的 GPLv2 全文是根目录 `LICENSE`）：

| 文件 | 覆盖组件 |
| --- | --- |
| `licenses/GPL-2.0.txt` | John the Ripper |
| `licenses/LGPL-2.1.txt` | 7-Zip |
| `licenses/7-Zip-LICENSE.txt` | 7-Zip 分文件许可说明 |
| `licenses/unRAR-restriction.txt` | unRAR 限制条款 |
| `licenses/hashcat-license.txt` | hashcat |
| `licenses/hashcat-license_libs/` | hashcat 静态链接的第三方库 |

## 源码获取（书面要约）

分发包里是未经修改的上游构建，源码地址写在 `licenses/README.md`。地址失效或需要我们直接提供副本时，
在仓库提 issue 即可，我们会在合理时间内提供（GPLv2 §3、LGPL-2.1 §6）。

## 分发时你必须做到

1. 附上本文件、`licenses/` 与 `LICENSE`（包内另有 `LICENSES.txt` 作入口），不得删改第三方版权声明。
2. 分发 john / 7-Zip / hashcat 的二进制时，必须同时提供对应源码或书面要约；`licenses/README.md` 就是要约正文。
3. 不得声称整个分发包仅由 GPL-2.0 覆盖——GPL 只覆盖我们的驱动代码，第三方组件各自独立。
4. UnRAR 仅可用于解包/校验，不得用于实现 RAR 压缩。

## 我们分发的 hashcat 模块

只保留压缩包相关模式，其余模式模块未随包分发：
11600（7z）、12500（RAR3-hp）、13000（RAR5）、13600（WinZip AES）、
17200 / 17210 / 17220 / 17225 / 17230（PKZIP）、23700 / 23800（RAR3-p）。

## 合规说明

驱动与被调用引擎之间没有链接、没有共享内存、没有代码合并，只通过命令行参数与标准输出交互，
因此属于 GPLv2 §2 所述的“mere aggregation（单纯聚合）”。若你修改了驱动并对外分发，
需要以 GPL-2.0-or-later 提供修改后的源码。
