#!/usr/bin/env bash
# 模式识别回归：用 hashcat --example-hashes -m <mode> --mach 取完整例哈希喂给
# crumbs.resolve_hashcat_mode，断言不截断、不退回签名猜测。
set -u
cd "$(dirname "$0")/.." || exit 1
HASHCAT="$(command -v hashcat || true)"
if [ -z "$HASHCAT" ]; then
    echo "SKIP: hashcat not found on PATH" >&2
    exit 77
fi
python3 - "$HASHCAT" <<'PY'
import contextlib
import io
import json
import re
import subprocess
import sys

sys.path.insert(0, ".")
import crumbs

hc = sys.argv[1]
cases = [
    (13600, "zip", "$zip2$"),
    (17220, "zip", "$pkzip2$"),
    (11600, "7z", "$7z$"),
    (13000, "rar5", "$rar5$"),
]
failed = 0
for expected, fmt, sigil in cases:
    ex = subprocess.run(
        [hc, "--example-hashes", "-m", str(expected), "--mach"],
        capture_output=True, text=True, errors="replace",
    )
    out = ex.stdout + "\n" + ex.stderr
    m = re.search(r'"example_hash"\s*:\s*"((?:\\.|[^"\\])*)"', out)
    if not m:
        print("[FAIL] mode %d: --mach example_hash not found" % expected)
        failed += 1
        continue
    example = json.loads('"%s"' % m.group(1))
    stderr_buf = io.StringIO()
    with contextlib.redirect_stderr(stderr_buf):
        got, candidates = crumbs.resolve_hashcat_mode(hc, [example], fmt)
    fallback_warned = bool(stderr_buf.getvalue().strip())
    status = "OK " if got == str(expected) and not fallback_warned else "FAIL"
    print("[%s] mode %d sigil %s -> resolved %s candidates %s" % (status, expected, sigil, got, candidates))
    print("      example: %s" % example[:90])
    if got != str(expected) or fallback_warned:
        failed += 1
    if expected == 17220 and candidates != [17220]:
        print("[FAIL] mode 17220 candidates %s != [17220]" % candidates)
        failed += 1
sys.exit(1 if failed else 0)
PY
