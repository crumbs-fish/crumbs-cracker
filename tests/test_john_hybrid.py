#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""john hybrid 回归测试：用 tests/stubs 桩验证 dry-run 命令形态。

覆盖：
- engine=john + -a hybrid 生成 [john, --stdin, --mask=?w<mask>, --pot=..., hashfile]
  且 stdin 指向 wordlist（不再抛 "hybrid 需要 hashcat"）
- hashcat 路径不变：engine=hashcat + -a hybrid 仍是 -a 6 + wordlist + mask
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CRUMBS = ROOT / "crumbs_cracker.py"
STUBS = ROOT / "tests" / "stubs"
FIXTURE = ROOT / "tests" / "fixtures" / "encrypted.zip"


def run_dry(args, cfg_path):
    proc = subprocess.run(
        [sys.executable, str(CRUMBS), "crack", str(FIXTURE),
         "-a", "hybrid", "-w", args["words"], "-m", args["mask"],
         "--dry-run", "--json", "--engines", str(cfg_path)],
        cwd=str(ROOT), capture_output=True, text=True, errors="replace",
    )
    if proc.returncode != 0:
        print("[FAIL] rc=%d stderr=%s" % (proc.returncode, proc.stderr.strip()[:300]))
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        print("[FAIL] 输出不是 JSON: %s" % proc.stdout[:300])
        return None


def main():
    tmp = Path(tempfile.mkdtemp(prefix="crumbs_test_"))
    words = tmp / "words.txt"
    words.write_text("secret\nwrong\n", encoding="utf-8")
    john_cfg = tmp / "john_cfg.json"
    john_cfg.write_text(json.dumps({
        "john_bin": str(STUBS / "john"),
        "zip2john": str(STUBS / "zip2john"),
        "rar2john": str(STUBS / "zip2john"),
        "sevenz2john": str(STUBS / "zip2john"),
        "gpu_available": False,
    }), encoding="utf-8")
    hc_cfg = tmp / "hc_cfg.json"
    hc_cfg.write_text(json.dumps({
        "hashcat_bin": str(STUBS / "hashcat"),
        "zip2john": str(STUBS / "zip2john"),
        "rar2john": str(STUBS / "zip2john"),
        "sevenz2john": str(STUBS / "zip2john"),
        "gpu_available": True,
    }), encoding="utf-8")
    failed = 0

    data = run_dry({"words": str(words), "mask": "?d?d"}, john_cfg)
    if data is None:
        return 1
    crack = data["commands"]["crack"]
    if data["engine"] != "john" or "--stdin" not in crack or "--mask=?w?d?d" not in crack:
        print("[FAIL] john hybrid crack 命令错误: %s" % crack)
        failed += 1
    if data["commands"].get("stdin") != str(words):
        print("[FAIL] john hybrid stdin 未标明 wordlist: %s" % data["commands"].get("stdin"))
        failed += 1

    data = run_dry({"words": str(words), "mask": "?d?d"}, hc_cfg)
    if data is None:
        return 1
    crack = data["commands"]["crack"]
    if data["engine"] != "hashcat" or "-a" not in crack or "6" not in crack:
        print("[FAIL] hashcat hybrid 不再使用 -a 6: %s" % crack)
        failed += 1
    if "--stdin" in crack:
        print("[FAIL] hashcat hybrid 不应出现 --stdin: %s" % crack)
        failed += 1

    if failed:
        return 1
    print("[OK] john hybrid --stdin/--mask 命令 + hashcat -a 6 路径不变")
    return 0


if __name__ == "__main__":
    sys.exit(main())
