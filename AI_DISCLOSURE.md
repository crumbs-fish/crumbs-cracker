# 这个项目是怎么写出来的

先把话说明白：这个仓库里没有一行代码是人手写的。

整个 crumbs-cracker 由 AI 生成——DeepSeek Harness（DSH）平台上的 DeepSeek-V4-Pro 负责设计和实现，
DeepSeek-V4-Flash 作为子代理负责构建、核对和文档。时间跨度是 2026 年 11 月 10 日到 22 日。

人做的事情只有三件：提需求、定验收标准、在真机上跑测试。没有改过任何一行代码。

覆盖的范围：

- `crumbs_cracker.py`，驱动本体，约 67 KB
- `scripts/` 下的打包脚本和 Windows 引导脚本
- `tests/` 里的测试和样本重建脚本
- `docs/`、README、CHANGELOG 这些文档
- `dicts/` 的字典整理与去重

AI 写的代码有几个天生的短板，用之前心里有数：

1. 只在两种环境里验证过：Debian 12（2 核，无 GPU）和 Windows 10 + RTX 4060。别的发行版、
   别的显卡，没测过就是没测过。
2. 长会话迭代出来的代码，注释可能还在描述旧行为，一切以代码和测试为准。
3. hashcat 6.2.6 和 john-jumbo bleeding-37bebbe4b64 的 CLI 行为如果上游变了，这里要跟着改。
4. 没有做过模糊测试，也没专门拿恶意压缩包（zip 炸弹、路径穿越）试过。

如果你在这个基础上继续开发，请把这份说明和 LICENSE 一起保留，并在你的 README 里写一句
「基于 AI 生成的 crumbs-cracker（DeepSeek-V4-Pro）」。
