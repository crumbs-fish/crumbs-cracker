#!/usr/bin/env bash
# 把组装好的 Windows 暂存目录打成 7-Zip 自解压单文件（最大压缩比）。
# 用法: bash scripts/build-sfx-win.sh <暂存父目录> <7zCon.sfx> [输出文件名]
# 例:   bash scripts/build-sfx-win.sh /tmp/pw10 /tmp/sfxinst/7zCon.sfx
# 说明: 暂存父目录下必须有一个 crumbs-cracker-portable-win64/ 子目录，脚本会把整个子目录打进包里。
#       压缩参数 -mx=9 -m0=lzma2:d=64m:fb=273：实测 d=256m 只再小 0.02%，不值那 100 MB 内存。
set -euo pipefail

PARENT=${1:?用法: build-sfx-win.sh <暂存父目录> <7zCon.sfx> [输出文件名]}
SFX_MOD=${2:?缺少 SFX 模块（7-Zip 安装包里的 7zCon.sfx）}
NAME=${3:-crumbs-cracker-portable-win64-sfx.exe}

REPO=$(cd "$(dirname "$0")/.." && pwd)
SZ="$REPO/dist/crumbs-cracker-portable/engines/bin/7zz"
[ -x "$SZ" ] || SZ=$(command -v 7zz || command -v 7z)
[ -x "$SZ" ] || { echo "找不到 7zz/7z" >&2; exit 1; }
[ -f "$SFX_MOD" ] || { echo "找不到 SFX 模块: $SFX_MOD" >&2; exit 1; }
[ -d "$PARENT/crumbs-cracker-portable-win64" ] || { echo "暂存目录不完整: $PARENT/crumbs-cracker-portable-win64" >&2; exit 1; }

OUT="$PARENT/$NAME"
rm -f "$OUT"
( cd "$PARENT" && "$SZ" a -t7z -mx=9 -m0=lzma2:d=64m:fb=273 -mmt=2 \
    "-sfx$SFX_MOD" "$OUT" crumbs-cracker-portable-win64 -bso0 -bsp0 )

"$SZ" t "$OUT" >/dev/null
echo "$OUT  $(stat -c%s "$OUT") B  sha256=$(sha256sum "$OUT" | cut -d' ' -f1)"
