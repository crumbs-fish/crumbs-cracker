#!/usr/bin/env bash
# 在 arm64 Linux（含 Switch OLED 的 switchroot Ubuntu、树莓派一类单板机）上准备引擎。
# 这里全部走系统仓库，不需要编译。
#
#   bash scripts/build-switchroot.sh            装引擎并自检
#   bash scripts/build-switchroot.sh --no-test  只装引擎
#
# 这类设备没有可用的 OpenCL 运行时，所以只有 CPU（john），hashcat 起不来也不用管。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_TEST=1
[ "${1:-}" = "--no-test" ] && RUN_TEST=0

info() { printf '\033[36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33m注意\033[0m %s\n' "$*"; }
die()  { printf '\033[31m错误\033[0m %s\n' "$*" >&2; exit 1; }

command -v apt-get >/dev/null 2>&1 || die "这个脚本按 Debian/Ubuntu 写的（需要 apt-get）"
[ "$(uname -m)" = "aarch64" ] || warn "当前架构是 $(uname -m)，不是 arm64，也能装但请你确认一下"

SUDO=""
[ "$(id -u)" -ne 0 ] && SUDO="sudo"
[ -n "$SUDO" ] && ! command -v sudo >/dev/null 2>&1 && die "需要 root 或 sudo 来装包"

info "apt 安装 john / p7zip-full / perl"
$SUDO apt-get update -qq
$SUDO apt-get install -y john p7zip-full perl
if ! $SUDO apt-get install -y unrar >/dev/null 2>&1; then
    $SUDO apt-get install -y unrar-free >/dev/null 2>&1 || warn "unrar / unrar-free 都没装上，rar 复核会用 7z 代替"
fi

find_bin() {
    for name in "$@"; do
        p="$(command -v "$name" 2>/dev/null || true)"
        [ -n "$p" ] && { echo "$p"; return 0; }
        for d in /usr/sbin /usr/bin /usr/local/sbin /usr/local/bin; do
            [ -x "$d/$name" ] && { echo "$d/$name"; return 0; }
        done
    done
    return 1
}

JOHN="$(find_bin john)" || die "装完还是找不到 john"
ZIP2JOHN="$(find_bin zip2john)" || die "找不到 zip2john（john 的 jumbo 工具没装？）"
RAR2JOHN="$(find_bin rar2john)" || die "找不到 rar2john"
SEVENZ="$(find_bin 7z 7zz)" || die "找不到 7z（p7zip-full 没装上？）"
UNRAR="$(find_bin unrar unrar-free || true)"

SEVENZ2JOHN=""
for cand in "$(dirname "$JOHN")/7z2john.pl" /usr/share/john/7z2john.pl /usr/lib/john/7z2john.pl; do
    [ -f "$cand" ] && { SEVENZ2JOHN="$cand"; break; }
done
[ -z "$SEVENZ2JOHN" ] && warn "没找到 7z2john.pl，7z 格式会提取失败（zip / rar 不受影响）"

info "写 engines/engines.json"
mkdir -p "$ROOT/engines"
python3 - "$ROOT" "$JOHN" "$ZIP2JOHN" "$RAR2JOHN" "$SEVENZ2JOHN" "$SEVENZ" "$UNRAR" <<'PY'
import json, os, sys
root, john, z2j, r2j, s2j, sevenz, unrar = sys.argv[1:8]
cfg = {
    "john_bin": john,
    "zip2john": z2j,
    "rar2john": r2j,
    "sevenz2john": s2j,
    "sevenz_bin": sevenz,
    "unrar_bin": unrar,
    "rar_bin": unrar,
    "perl_bin": "perl",
    "hashcat_bin": "",
    "gpu_available": False,
    "gpu_devices": [],
    "notes": "arm64 Linux（switchroot / 单板机）：apt 装的 john 与 p7zip，绝对路径；只有 CPU 引擎",
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
