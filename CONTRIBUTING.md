# 贡献指南

欢迎开 issue 和提 PR。这个项目很小，规矩也简单：

1. Fork 之后从 main 拉个分支，名字随意，`feat/xxx`、`fix/xxx` 都行。
2. 一个 PR 只解决一件事。驱动继续保持单文件、只用标准库。
3. 动手前先跑一遍测试，别让 CI 替你发现低级问题：

```bash
python3 tests/test_keyspace.py
python3 tests/test_gpu_hashcat.py
bash tests/test_mode_identify.sh
```

4. 改动涉及引擎调用的，PR 描述里贴一下实际命令和输出（什么格式、哪个引擎、命中还是没命中），
   光说「本地过了」不好复现。
5. 提交信息用 `feat:/`、`fix:/`、`docs:/`、`test:/` 前缀。

几个一直守着的约定：

- 子进程一律用 subprocess 列表参数，不允许 shell=True 拼字符串
- 读写文件和子进程输出统一 `encoding='utf-8', errors='replace'`
- 路径用 pathlib，项目根用 `Path(__file__).resolve().parent`
- 给用户看的输出写中文，JSON 字段名保持英文，退出码 0/1/2
