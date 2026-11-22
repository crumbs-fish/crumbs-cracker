# 贡献指南

1. Fork 并新建分支：feat/xxx 或 fix/xxx。
2. 每个 PR 只改一个关注点，保持「单文件、仅标准库」的约束。
3. 提交前跑完：

~~~bash
python3 tests/test_keyspace.py
python3 tests/test_gpu_hashcat.py
bash tests/test_mode_identify.sh
~~~

4. 涉及引擎调用的改动，请在 PR 描述里贴出实际命令与输出（格式、引擎、命中或未命中）。
5. 提交信息用 feat: / fix: / docs: / test: 前缀。

## 代码约定

- 子进程一律 subprocess 列表参数，禁止 shell=True 拼接
- 文本读写与子进程输出统一 encoding='utf-8', errors='replace'
- 路径一律 pathlib.Path，项目根用 Path(__file__).resolve().parent
- 面向用户的输出中文，JSON 字段名英文，退出码 0/1/2
