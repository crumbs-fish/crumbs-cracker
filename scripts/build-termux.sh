#!/usr/bin/env bash
# 在 Termux（Android arm64）里准备引擎：john 现场编译，7zip / unrar / perl 走 pkg 安装。
#
#   bash scripts/build-termux.sh            装引擎并自检
#   bash scripts/build-termux.sh --no-test  只装引擎，不跑自检
#
# 编译要 10-30 分钟、约 1.5 GB 空间。装完 python3 crumbs_cracker.py 就能直接跑。
# 安卓非 root 拿不到厂商 OpenCL，所以这里只装 CPU 引擎（john），不装 hashcat。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JOHN_REPO="${JOHN_REPO:-https://github.com/openwall/john}"
JOHN_COMMIT="${JOHN_COMMIT:-37bebbe4b6442c8dd3888e5848ef062c0783e9f3}"
SRC="${JOHN_SRC:-$HOME/.cache/crumbs-john}"
RUN_TEST=1
[ "${1:-}" = "--no-test" ] && RUN_TEST=0

info() { printf '\033[36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33m注意\033[0m %s\n' "$*"; }
die()  { printf '\033[31m错误\033[0m %s\n' "$*" >&2; exit 1; }

command -v pkg >/dev/null 2>&1 || die "这个脚本要在 Termux 里跑（找不到 pkg 命令）"
[ "$(uname -m)" = "aarch64" ] || warn "当前架构是 $(uname -m)，脚本按 aarch64 写的，继续试"

info "安装依赖（python clang make perl pkg-config 7zip unrar git openssl liblzma）"
pkg update -y >/dev/null 2>&1 || true
pkg install -y python clang make perl pkg-config 7zip unrar git openssl liblzma

info "取 john-jumbo 源码到 $SRC"
if [ -d "$SRC/.git" ]; then
    git -C "$SRC" fetch --depth 1 origin "$JOHN_COMMIT" >/dev/null 2>&1 || true
else
    mkdir -p "$(dirname "$SRC")"
    git clone --filter=blob:none "$JOHN_REPO" "$SRC"
fi
git -C "$SRC" checkout -q "$JOHN_COMMIT" || die "切不到 $JOHN_COMMIT"

JOBS="$(nproc 2>/dev/null || echo 4)"
[ "$JOBS" -gt 6 ] && JOBS=6

info "编译 john（-j$JOBS，第一次要十几分钟，输出写 $HOME/.cache/crumbs-john-build.log）"
mkdir -p "$HOME/.cache"
cd "$SRC/src"
if ! ./configure --disable-native-tests >"$HOME/.cache/crumbs-john-conf.log" 2>&1; then
    tail -20 "$HOME/.cache/crumbs-john-conf.log" >&2
    die "configure 失败，完整日志 $HOME/.cache/crumbs-john-conf.log"
fi
if ! make -s -j"$JOBS" >"$HOME/.cache/crumbs-john-build.log" 2>&1; then
    tail -30 "$HOME/.cache/crumbs-john-build.log" >&2
    die "make 失败，完整日志 $HOME/.cache/crumbs-john-build.log"
fi

info "拷进 engines/john/run"
mkdir -p "$ROOT/engines/john/run"
for bin in john zip2john rar2john; do
    [ -x "$SRC/run/$bin" ] || die "没编出 $bin"
    install -m 0755 "$SRC/run/$bin" "$ROOT/engines/john/run/$bin"
done
for f in 7z2john.pl john.conf; do
    [ -f "$SRC/run/$f" ] && install -m 0644 "$SRC/run/$f" "$ROOT/engines/john/run/$f"
done

info "检查 7z 提取器要的 perl 模块 Compress::Raw::Lzma"
if perl -MCompress::Raw::Lzma -e1 >/dev/null 2>&1; then
    echo "    已有，7z 可以提取"
else
    echo "    缺，尝试 cpan 装（几分钟，可能失败）"
    if cpan -T Compress::Raw::Lzma >/dev/null 2>&1 && perl -MCompress::Raw::Lzma -e1 >/dev/null 2>&1; then
        echo "    装好了"
    else
        warn "没装上：7z 格式暂时不能提取，zip / rar 不受影响"
    fi
fi

SEVENZ="$(command -v 7zz || command -v 7z || true)"
UNRAR="$(command -v unrar || true)"
[ -n "$SEVENZ" ] || die "没找到 7z / 7zz"
[ -n "$UNRAR" ] || warn "没找到 unrar，rar 复核会退回用 7z"

info "写 engines/engines.json"
mkdir -p "$ROOT/engines"
python3 - "$ROOT" "$SEVENZ" "$UNRAR" <<'PY'
import json, os, sys
root, sevenz, unrar = sys.argv[1], sys.argv[2], sys.argv[3]
cfg = {
    "john_run_dir": "john/run",
    "john_bin": "john/run/john",
    "zip2john": "john/run/zip2john",
    "rar2john": "john/run/rar2john",
    "sevenz2john": "john/run/7z2john.pl",
    "sevenz_bin": sevenz,
    "unrar_bin": unrar,
    "rar_bin": unrar,
    "perl_bin": "perl",
    "hashcat_bin": "",
    "gpu_available": False,
    "gpu_devices": [],
    "notes": "Termux/arm64：只有 CPU 引擎（john），路径相对 engines.json 自身；7zip 与 unrar 用系统安装的位置",
}
path = os.path.join(root, "engines", "engines.json")
with open(path, "w", encoding="utf-8") as fh:
    json.dump(cfg, fh, ensure_ascii=False, indent=2)
    fh.write("\n")
print("    写入", path)
PY

if [ "$RUN_TEST" = "0" ]; then
    info "跳过自检（--no-test）"
    exit 0
fi

info "自检：造一个密码 secret 的 zip，走一遍 check 和字典破解"
TMPD="$(mktemp -d)"
trap 'rm -rf "$TMPD"' EXIT
printf 'hello\n' > "$TMPD/t.txt"
"$SEVENZ" a -tzip -mem=ZipCrypto -psecret "$TMPD/t.zip" "$TMPD/t.txt" >/dev/null
printf 'wrongpass\nsecret\n' > "$TMPD/words.txt"
python3 "$ROOT/crumbs_cracker.py" check "$TMPD/t.zip"
python3 "$ROOT/crumbs_cracker.py" crack -a wordlist -w "$TMPD/words.txt" "$TMPD/t.zip"

info "完事。用法：cd $ROOT && python3 crumbs_cracker.py --help"
