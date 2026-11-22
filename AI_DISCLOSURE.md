# AI 生成声明（AI Disclosure）

本仓库没有任何人工编写的代码。以下全部由 AI Agent 生成，人类只负责提出需求与验收。

## 生成主体

| 项 | 值 |
| --- | --- |
| 平台 | DeepSeek Harness（DSH） |
| 主模型 | **DeepSeek-V4-Pro** |
| 协作模型 | **DeepSeek-V4-Flash**（子代理） |
| 生成区间 | 2026-11-10 ～ 2026-11-22 |
| 交互语言 | 中文 |
| 人类贡献 | 需求描述、验收标准、真机测试环境；未修改代码 |

## 生成范围

- crumbs_cracker.py（约 67 KB，全部逻辑）
- scripts/*.sh、scripts/*.ps1（打包与 Windows 引导）
- tests/*（单元测试、样档重建）
- docs/*、README.md、CHANGELOG.md 等文档
- dicts/ 中的字典整理与去重

## AI 生成的已知风险

1. 过拟合测试环境：逻辑在 Debian 12（2 核）与 Windows 10 + RTX 4060 上验证，其他环境未覆盖。
2. 注释与实现漂移：长会话迭代中可能出现注释描述旧行为，以代码与测试为准。
3. 第三方版本锁定：hashcat 6.2.6 / john-jumbo bleeding-37bebbe4b64 的 CLI 行为若变化需同步调整。
4. 安全审计缺失：未做模糊测试，未专项测试恶意压缩包（zip 炸弹、路径穿越）。

## 如何引用

在本项目基础上二次开发时，请保留本文件与 LICENSE，并在 README 中注明「基于 AI 生成的 crumbs（DeepSeek-V4-Pro）」。
