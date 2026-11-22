# vendor 目录

7-Zip 23.01 自解压模块（Windows 包用，PE32）：

| 文件 | 大小 | 用途 |
| --- | --- | --- |
| 7zCon.sfx | 193,024 B | 控制台版自解压头（当前使用，`scripts/build-sfx-win.sh` 用它） |
| 7z.sfx | 214,528 B | GUI 版自解压头（备用） |

来源：官方安装包 https://www.7-zip.org/a/7z2301-x64.exe （1,589,510 B），
用 7-Zip 解开后取根目录的这两个文件（7z2301-extra.7z 里**没有** .sfx）。

校验：`sha256sum vendor/7zCon.sfx vendor/7z.sfx`（见 SHA256SUMS）。

重新获取：

```
curl -sL -o /tmp/7zsetup.exe https://www.7-zip.org/a/7z2301-x64.exe
7zz x -y /tmp/7zsetup.exe -o/tmp/sfxinst 7zCon.sfx 7z.sfx
```