# 随包许可证原文与源码获取

驱动本身是 GPL-2.0-or-later，全文在仓库根目录 `LICENSE`。本目录放的是随包分发的第三方组件的许可证原文。

| 文件 | 覆盖组件 |
| --- | --- |
| `GPL-2.0.txt` | John the Ripper（GPLv2+） |
| `LGPL-2.1.txt` | 7-Zip（LGPL-2.1+） |
| `7-Zip-LICENSE.txt` | 7-Zip 源码树的分文件许可说明（含 unRAR 限制与 BSD 部分） |
| `unRAR-restriction.txt` | 7-Zip 内 unRAR 解压代码的限制条款 |
| `hashcat-license.txt` | hashcat（MIT） |
| `hashcat-license_libs/` | hashcat 静态链接的库：LZMA SDK、miniz、OpenCL headers、unrar、xxHash、zlib |

## 源码获取（书面要约）

分发包里是**未经修改的上游构建**，对应源码：

- John the Ripper jumbo，commit `37bebbe4b6442c8dd3888e5848ef062c0783e9f3`：https://github.com/openwall/john/tree/37bebbe4b6442c8dd3888e5848ef062c0783e9f3
- hashcat 6.2.6：https://github.com/hashcat/hashcat/tree/v6.2.6
- 7-Zip 23.01：https://www.7-zip.org/a/7z2301-src.7z
- UnRAR 6.2.4：https://www.rarlab.com/rar/unrarsrc-6.2.4.tar.gz
- 7z2hashcat 2.0（Windows 包）：https://github.com/philsmd/7z2hashcat
- Python 3.12 embeddable（Windows 包）：https://www.python.org/downloads/windows/

上面这些地址失效，或者你需要我们直接提供对应的源码副本，在仓库提一个 issue 就行，
我们会在合理时间内提供（对应 GPLv2 §3 与 LGPL-2.1 §6 的书面要约）。
