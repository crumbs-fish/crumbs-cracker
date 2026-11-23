#!/usr/bin/env bash
# 构建 Linux x86-64 便携包。用法： scripts/build-portable.sh [输出目录，默认 dist]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/dist}"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
STAGE="$OUT/crumbs-cracker-portable"
VER="$(date +%Y%m%d)"

rm -rf "$STAGE"
mkdir -p "$STAGE/engines/john/run" "$STAGE/engines/bin" "$STAGE/engines/vendor" "$STAGE/engines/hashcat/modules" "$STAGE/docs" "$STAGE/samples" "$STAGE/dicts"
cp -a "$ROOT/dicts/." "$STAGE/dicts/"

install -m 0755 "$ROOT/crumbs_cracker.py" "$STAGE/crumbs_cracker.py"
install -m 0755 "$ROOT/crumbs-cracker.sh" "$STAGE/crumbs-cracker.sh"
install -m 0644 "$ROOT/docs/USAGE.md" "$STAGE/docs/USAGE.md"
[ -f "$ROOT/README.md" ] && install -m 0644 "$ROOT/README.md" "$STAGE/docs/README.md"

# --- john：主二进制 + 提取器包装（john 是单二进制，按 argv[0] 分派）---
JR="$ROOT/engines/john/run"
install -m 0755 "$JR/john" "$STAGE/engines/john/run/john"
for l in zip2john rar2john; do
  printf '#!/bin/bash\nexec -a %s "$(dirname "$0")/john" "$@"\n' "$l" > "$STAGE/engines/john/run/$l"
  chmod 0755 "$STAGE/engines/john/run/$l"
done
install -m 0644 "$JR/john.conf" "$STAGE/engines/john/run/john.conf"
for f in "$JR"/*.conf; do
  b="$(basename "$f")"; [ "$b" = john.conf ] || install -m 0644 "$f" "$STAGE/engines/john/run/$b"
done
cp -a "$JR/rules" "$STAGE/engines/john/run/rules"
install -m 0644 "$JR/7z2john.pl" "$STAGE/engines/john/run/7z2john.pl"

# --- 7z2john 包装器 ---
cat > "$STAGE/engines/bin/7z2john" <<'EOS'
#!/bin/sh
E=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
INC=""
for d in "$E"/vendor/perl5/*/lib/*/perl5/* "$E"/vendor/perl5/*/share/perl5/*; do
  [ -d "$d" ] && INC="$INC -I$d"
done
exec perl $INC "$E/john/run/7z2john.pl" "$@"
EOS
chmod 0755 "$STAGE/engines/bin/7z2john"

cp -a "$ROOT/engines/vendor/perl5" "$STAGE/engines/vendor/" 2>/dev/null || true
# 7-Zip 静态单文件版（p7zip 的 7z 需要同目录 7z.so，不能单独拷走）
SEVENZ_SRC="${SEVENZ_SRC:-/tmp/7zzdl/7zz}"
if [ -x "$SEVENZ_SRC" ]; then
  install -m 0755 "$SEVENZ_SRC" "$STAGE/engines/bin/7zz"
else
  echo "warn: 缺少 ${SEVENZ_SRC}（静态 7-Zip），7z 复核将退化" >&2
fi
UNRAR_SRC="${UNRAR_SRC:-$(command -v unrar || true)}"
if [ -n "$UNRAR_SRC" ] && [ -x "$UNRAR_SRC" ]; then
  install -m 0755 "$(readlink -f "$UNRAR_SRC")" "$STAGE/engines/bin/unrar"
else
  echo "warn: 找不到 unrar，RAR 复核将退化为 7zz" >&2
fi

# --- hashcat（GPU 加速；只带压缩包族模块，完整包 259 MB 太大）---
HC_SRC="${HC_SRC:-/tmp/hcx3/hctiny}"
if [ -x "$HC_SRC/hashcat.bin" ]; then
  install -m 0755 "$HC_SRC/hashcat.bin" "$STAGE/engines/hashcat/hashcat.bin"
  install -m 0644 "$HC_SRC/hashcat.hcstat2" "$STAGE/engines/hashcat/hashcat.hcstat2"
  cp -a "$HC_SRC/OpenCL" "$STAGE/engines/hashcat/OpenCL"
  for m in 00000 11600 12500 13000 13600 17200 17210 17220 17225 17230 23700 23800; do
    install -m 0644 "$HC_SRC/modules/module_$m.so" "$STAGE/engines/hashcat/modules/module_$m.so"
  done
else
  echo "warn: 缺少 $HC_SRC（瘦身 hashcat），GPU 加速将不可用" >&2
fi

cat > "$STAGE/engines/engines.json" <<'EOS'
{
  "john_run_dir": "john/run",
  "john_bin": "john/run/john",
  "zip2john": "john/run/zip2john",
  "rar2john": "john/run/rar2john",
  "sevenz2john": "bin/7z2john",
  "sevenz_bin": "bin/7zz",
  "unrar_bin": "bin/unrar",
  "rar_bin": "bin/unrar",
  "perl_bin": "perl",
  "hashcat_bin": "hashcat/hashcat.bin",
  "gpu_available": false,
  "gpu_devices": [],
  "notes": "便携包：路径相对 engines.json 自身；gpu_available 只是提示，实际以 hashcat -I 运行时探测为准"
}
EOS

SAMPLES_DIR="${SAMPLES_DIR:-/tmp/crumbs_fx}"
for s in zipaes.zip zipcrypto.zip sevenz.7z rar4.rar rar5.rar mask.zip hybrid.zip words.txt words_bad.txt; do
  [ -f "$SAMPLES_DIR/$s" ] && install -m 0644 "$SAMPLES_DIR/$s" "$STAGE/samples/$s"
done
[ -f "$ROOT/scripts/portable-README.md" ] && cp "$ROOT/scripts/portable-README.md" "$STAGE/README.txt"
[ -f "$ROOT/scripts/portable-LICENSES.txt" ] && cp "$ROOT/scripts/portable-LICENSES.txt" "$STAGE/LICENSES.txt"
[ -f "$ROOT/LICENSE" ] && cp "$ROOT/LICENSE" "$STAGE/LICENSE"
[ -f "$ROOT/THIRD_PARTY_LICENSES.md" ] && cp "$ROOT/THIRD_PARTY_LICENSES.md" "$STAGE/THIRD_PARTY_LICENSES.md"

SEVENZIP="$STAGE/engines/bin/7zz"
[ -x "$SEVENZIP" ] || SEVENZIP=$(command -v 7z || command -v 7zz)
PKG="$OUT/crumbs-cracker-portable-linux-x64-$VER.7z"
rm -f "$PKG"
( cd "$OUT" && "$SEVENZIP" a -t7z -mx=7 -mmt=2 "$PKG" "$(basename "$STAGE")" -bso0 -bsp0 )
du -sh "$STAGE" "$PKG"
