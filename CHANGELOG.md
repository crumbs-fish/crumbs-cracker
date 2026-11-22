# 更新日志

## 1.0.0 - 2026-11-22

第一次公开。

**做了什么**

- 单文件驱动 `crumbs_cracker.py`：zip / 7z / rar4 / rar5 的识别、哈希提取、破解、明文复核
- 引擎自动选择：先探 GPU（`hashcat -I`），有就用 hashcat，没有就 john；跑到一半显存不够会自动切
- 三种攻击方式：字典、掩码、混合；长度未知可以逐位试（`--len-min` / `--len-max`）
- 组合数护栏：单轮超过 2^64 就按位截断，起始位就超限直接报错
- 不带参数运行时弹中文问答向导
- 两个便携包：Linux 的 .7z（john + 裁剪版 hashcat），Windows 的自解压 exe（连 Python 都带了）
- 内置字典：`dicts/common.txt`（1 万条）和 `dicts/common-100k.txt`（10 万条）

**开发期间修过的坑**

- zip AES 包被误判成未加密（原来只看了第一个条目，改成扫全部条目）
- RAR3-p 哈希（`$RAR3$*1*`）映射错模式导致 `No hashes loaded`，改用 23800
- john 输出 `文件:密码` 被解析成未命中，改用 `rsplit(':', 1)`
- 混合模式 `?w?d?d` 被展开成 `?w?w?d?d`，现在会先剥掉前导 `?w`
- Windows 包里 engines.json 的路径多了个 `engines/` 前缀
- 逐位模式在校验函数里被重复校验，组合数被平方
