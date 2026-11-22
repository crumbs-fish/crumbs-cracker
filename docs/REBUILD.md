# 以后改动怎么重打包（REBUILD）

目标：改完 `crumbs_cracker.py` / 文档后，能在几分钟内重新产出两个交付包，并跑完回归。

## 0. 现在有哪些东西是“必须留着”的

| 路径 | 作用 |
| --- | --- |
| `crumbs_cracker.py` | 唯一驱动（Python 标准库，单文件）；改逻辑只改它 |
| `scripts/build-portable.sh` | 打 Linux 便携包（7z，`-mx=7`） |
| `scripts/build-sfx-win.sh` | 打 Windows 自解压单文件（`-mx=9 -m0=lzma2:d=64m:fb=273`） |
| `vendor/7zCon.sfx` | Windows 自解压头（193,024 B，来自 7z2301-x64.exe） |
| `dist/crumbs-cracker-portable/` | Linux 打包暂存目录（含本包 7zz，打 SFX 也用它） |
| `/tmp/hcx4/hctiny` | 瘦身 hashcat（`HC_SRC` 默认值，build-portable.sh 依赖它）；丢了可用 apt 的 hashcat 6.2.6 重建：`/usr/bin/hashcat` + `/usr/lib/hashcat/modules/module_{00000,11600,12500,13000,13600,14000,17200,17210,17220,17225,17230,23700,23800}.so` + `/usr/share/hashcat/{hashcat.hcstat2,OpenCL/}` |
| `tests/` | `test_keyspace.py`、`test_gpu_hashcat.py`、`test_mode_identify.sh`、`tests/rebuild-fixtures.sh`（重建 /tmp/crumbs_fx 样本） |
| `/tmp/7zzdl/7zz` | 静态 7-Zip（打包与包内 7z 复核都用它；`https://www.7-zip.org/a/7z2301-linux-x64.tar.xz` 解出的 `7zz`） |
| `/tmp/crumbs_accept.sh` | 7 档案 × 3 断言的全链路验收（本机临时脚本，丢了就按 §4 重写） |

## 1. 改完代码先跑回归（约 3 分钟）

```
cd ~/文档/deepseek-harness/default-workspace/crumbs-cracker
python3 tests/test_keyspace.py        # 组合数上限 / 逐位截断
python3 tests/test_gpu_hashcat.py     # GPU 选择与回退（桩）
bash /tmp/crumbs_accept.sh            # 7 档案 × check/correct/bad = 21 条
```

样本不在就先 `bash tests/rebuild-fixtures.sh`（重建 `/tmp/crumbs_fx`，密码 secret / 1234 / secret42）。

## 2. Linux 包

```
bash scripts/build-portable.sh
# 产物：dist/crumbs-cracker-portable-linux-x64-<日期>.7z（约 9.9 MB）
```

- `HC_SRC` 默认 `/tmp/hcx4/hctiny`；换机器时把它指向任意一份瘦身 hashcat 目录（含 `hashcat.bin`、`hashcat.hcstat2`、`OpenCL/`、`modules/module_*.so`）。
- 包内必须有：`run/` + `rules/`（john）、`bin/7z.exe|7z.dll`、`bin/7z2hashcat.exe`、`vendor/perl5`（7z2john 用）、`python` 不需要（Linux 用系统 python3）。

## 3. Windows 包（自解压单文件）

暂存目录不必从零搭：**从现有包里解出来就是完整基线**。

```
7zz x -y -o/tmp/pw11 crumbs-cracker-portable-win64-sfx-20261122.exe
# 得到 /tmp/pw11/crumbs-cracker-portable-win64/（1731 个文件，187 MB）

cp -f crumbs_cracker.py              /tmp/pw11/crumbs-cracker-portable-win64/crumbs_cracker.py
cp -f docs/USAGE.md          /tmp/pw11/crumbs-cracker-portable-win64/docs/USAGE.md
cp -f scripts/portable-README-win.md /tmp/pw11/crumbs-cracker-portable-win64/README.txt

bash scripts/build-sfx-win.sh /tmp/pw11 vendor/7zCon.sfx
# 产物：/tmp/pw11/crumbs-cracker-portable-win64-sfx.exe（约 34.4 MB，83 s，峰值内存 708 MB）
```

打包后自检：

```
7zz t /tmp/pw11/crumbs-cracker-portable-win64-sfx.exe          # Everything is Ok
7zz e -so /tmp/pw11/...-sfx.exe crumbs-cracker-portable-win64/crumbs_cracker.py | sha256sum
sha256sum crumbs_cracker.py                                          # 两处必须相同
```

Windows 真机验证（可选，链路慢）：只推 `crumbs_cracker.py` 过去即可证明行为一致——
`certutil -hashfile C:\crumbs-cracker\crumbs_cracker.py SHA256` 与仓库比对，再跑两条命令；
34 MB 整包在这条链路上约 15 分钟且容易中途停滞。

## 4. 交付与记录

```
cp dist/crumbs-cracker-portable-linux-x64-<日期>.7z  /home/coulddisk/压缩包爆破/
cp /tmp/pw11/crumbs-cracker-portable-win64-sfx.exe   /home/coulddisk/压缩包爆破/crumbs-cracker-portable-win64-sfx-<日期>.exe
cd /home/coulddisk/压缩包爆破 && sha256sum *.7z *.exe   # 同步写同名 .sha256
cp README.md USAGE.md DELIVERY.md STATUS-*.md portable-README-*.md win-bootstrap.md /home/coulddisk/压缩包爆破/
```

文档要一起更新：`-h`（`USAGE_MAIN`/`USAGE_CRACK`）、`docs/USAGE.md`、`README.md` 的“分发产物”表、`docs/STATUS-*.md` 追加一节。

## 5. 踩过的坑（别再踩）

- `pkill -f "scp -P 2222 .*pkg.exe"` 会匹配到自己那条 bash 并把它杀掉，后续命令不执行；清传输进程要换特征串，或先 `job_kill`。
- SFX 的 `-o` 经 ssh → cmd 多一层转义会变 `-o\C:\...`，报“文件名、目录名或卷标语法不正确”；稳妥写法是 `cd /d` 到父目录用相对路径 `-osfxout`，或本机 cmd 里 `-o"D:\tools" -y`。
- 逐位尝试的长度上限是 16（`--len-min/--len-max` 超了会先报参数错，不是组合数问题）；组合数单轮上限 2^64≈1.8e19，超了按位截断。
- 便携包 `engines.json` 的路径相对 `engines/` 目录，别写成 `engines/engines/...`。
- 中文控制台里用 `findstr` 搜中文常搜不到（编码问题），改把输出重定向到日志再回本地 grep；文件校验一律 `certutil -hashfile`。
- 打包参数别乱调：`-mx=9 -m0=lzma2:d=256m` 只比 `d=64m` 小 0.02%，却要多花 100 MB 内存。