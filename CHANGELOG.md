# 更新日志

## [1.0.0] - 2026-11-22

首个公开版本。

### 新增

- 跨平台驱动 crumbs_cracker.py：zip / 7z / rar4 / rar5 识别、哈希提取、破解、明文复核
- 引擎自动选择：GPU 探测（hashcat -I）→ hashcat，否则 john；运行时显存不足自动切 john
- 三种攻击方式：字典、掩码、混合；--len-min/--len-max 逐位尝试
- 组合数护栏：单轮超过 2^64 按位截断；起始位即超限则直接报错
- 中文交互向导（不带参数运行）
- 两份便携包：Linux .7z（john + 瘦身 hashcat）、Windows 自解压 .exe（含 Python 运行时）
- 内置字典 dicts/common.txt（1 万条）、dicts/common-100k.txt（10 万条）

### 修复（开发期）

- zip AES 包被误判为未加密：只检查首个条目 → 扫描全部条目
- RAR3-p 哈希（$RAR3$*1*）映射到 12500 导致 No hashes loaded → 改用 23800
- john 输出解析把 文件:密码 误判为未命中 → 改用 rsplit(':', 1)
- 混合模式 ?w?d?d 被展开成 ?w?w?d?d → 剥离前导 ?w
- engines.json 路径重复 engines/ 前缀（Windows 包）
- 逐位模式在 _crack_body 中重复校验导致组合数被平方
