#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GPU/hashcat 桩测试：探测优先、mask 破解、GPU 失败回退/报错、potfile 隔离、向导分支。"""
import builtins
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
CRUMBS = ROOT / "crumbs_cracker.py"
STUBS = ROOT / "tests" / "stubs"
FIXTURE = ROOT / "tests" / "fixtures" / "encrypted.zip"
sys.path.insert(0, str(ROOT))
import crumbs_cracker as crumbs

FAILED = 0


def check(label, cond, msg):
    global FAILED
    if not cond:
        print("[FAIL] %s: %s" % (label, msg))
        FAILED += 1
        return False
    print("[OK] %s" % label)
    return True


def make_cfg(tmp, with_john=False):
    cfg = {"hashcat_bin": str(STUBS / "hashcat"), "zip2john": str(STUBS / "zip2john"),
           "rar2john": str(STUBS / "zip2john"), "sevenz2john": str(STUBS / "zip2john"),
           "gpu_available": False}
    if with_john:
        cfg["john_bin"] = str(STUBS / "john")
    path = tmp / "engines.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path


def run_crack(cfg_path, env_extra, extra_args=None):
    argv = [sys.executable, str(CRUMBS), "crack", str(FIXTURE), "-a", "mask",
            "-m", "?d?d", "--json", "--engines", str(cfg_path)] + (extra_args or [])
    env = dict(os.environ)
    env.update(env_extra)
    proc = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True,
                          errors="replace", env=env)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        data = None
    return proc, data


def test_select_engine_gpu_despite_cfg_false():
    crumbs._GPU_PROBE_CACHE.clear()
    os.environ["CRUMBS_STUB_GPU"] = "1"
    try:
        probe = crumbs.probe_gpu(str(STUBS / "hashcat"))
        ok_probe = probe["available"] is True and any("GTX 1650" in d for d in probe["devices"])
        tools = {"hashcat": str(STUBS / "hashcat"), "john": str(STUBS / "john")}
        engine, backend, warning = crumbs.select_engine(tools, {"gpu_available": False}, "auto", True)
        check("select_engine 在 gpu_available=false 时探测出 GPU -> ('hashcat','gpu',None)",
              ok_probe and (engine, backend, warning) == ("hashcat", "gpu", None),
              (probe, engine, backend, warning))
    finally:
        os.environ.pop("CRUMBS_STUB_GPU", None)


def test_forced_hashcat_cpu_warning():
    crumbs._GPU_PROBE_CACHE.clear()
    os.environ["CRUMBS_STUB_GPU"] = "0"
    try:
        tools = {"hashcat": str(STUBS / "hashcat"), "john": str(STUBS / "john")}
        engine, backend, warning = crumbs.select_engine(tools, {"gpu_available": False}, "hashcat", True)
        check("--engine hashcat 强制且无 GPU -> ('hashcat','cpu', 警告)",
              engine == "hashcat" and backend == "cpu" and warning and "未检测到 GPU" in warning,
              (engine, backend, warning))
    finally:
        os.environ.pop("CRUMBS_STUB_GPU", None)


def test_crack_gpu_found(tmp):
    proc, data = run_crack(make_cfg(tmp), {"CRUMBS_STUB_GPU": "1"})
    check("mask 桩破解 found=True engine=hashcat backend=gpu password=secret",
          proc.returncode == 0 and data and data.get("found") is True
          and data.get("engine") == "hashcat" and data.get("backend") == "gpu"
          and data.get("password") == "secret",
          "rc=%d data=%s stderr=%s" % (proc.returncode, data, proc.stderr.strip()[:200]))


def test_gpu_fail_auto_fallback(tmp):
    proc, data = run_crack(make_cfg(tmp, with_john=True),
                           {"CRUMBS_STUB_GPU": "1", "CRUMBS_STUB_HC_GPU_FAIL": "1"})
    ok = (proc.returncode == 0 and data and data.get("found") is True
          and data.get("engine") == "john" and data.get("backend") == "cpu"
          and data.get("warning") and "自动改用 john" in proc.stderr)
    check("GPU 内存失败 auto -> john 重跑 found=True 且 warning 非空", ok,
          "rc=%d data=%s stderr=%s" % (proc.returncode, data, proc.stderr.strip()[:200]))


def test_gpu_fail_forced_error(tmp):
    proc, _ = run_crack(make_cfg(tmp, with_john=True),
                        {"CRUMBS_STUB_GPU": "1", "CRUMBS_STUB_HC_GPU_FAIL": "1"},
                        extra_args=["--engine", "hashcat"])
    check("--engine hashcat 强制时 GPU 失败 rc=2 且报 hashcat 运行失败",
          proc.returncode == 2 and "hashcat 运行失败" in proc.stderr,
          "rc=%d stderr=%s" % (proc.returncode, proc.stderr.strip()[:200]))


def test_potfile_tempdir_cleanup(tmp):
    log = tmp / "potdirs.log"
    env = {"CRUMBS_STUB_GPU": "1", "CRUMBS_STUB_LOG_POTDIR": str(log)}
    for _ in range(2):
        proc, data = run_crack(make_cfg(tmp), env)
        if proc.returncode != 0 or not data or data.get("found") is not True:
            check("potfile 隔离测试破解失败", False, "rc=%d data=%s" % (proc.returncode, data))
            return
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    dirs = [Path(x) for x in lines]
    ok = (len(dirs) == 2 and dirs[0] != dirs[1]
          and all(d.name.startswith("crumbs_hc_") for d in dirs)
          and not any(d.exists() for d in dirs))
    check("每次 hashcat 调用独立临时目录且退出后均已删除", ok,
          "dirs=%s" % [str(d) for d in dirs])


def run_wizard(cfg_dir, answers, env_gpu):
    crumbs._GPU_PROBE_CACHE.clear()
    os.environ["CRUMBS_STUB_GPU"] = env_gpu
    old_input, old_read = builtins.input, crumbs.read_engines
    cfg = json.loads((cfg_dir / "engines.json").read_text(encoding="utf-8"))
    it = iter(answers)
    builtins.input = lambda prompt="": next(it)
    crumbs.read_engines = lambda explicit=None: (cfg, str(cfg_dir))
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = crumbs.run_wizard(str(FIXTURE))
    finally:
        builtins.input, crumbs.read_engines = old_input, old_read
        os.environ.pop("CRUMBS_STUB_GPU", None)
    return rc, out.getvalue(), err.getvalue()


def test_wizard_gpu_yes_and_no(tmp):
    cfg_dir = tmp / "wiz"
    cfg_dir.mkdir()
    make_cfg(cfg_dir, with_john=True)
    answers = ["2", "4", "1", "y", "n"]
    rc, out, _ = run_wizard(cfg_dir, answers, "1")
    ok = (rc == 2 and "已检测到 GPU: NVIDIA GeForce GTX 1650" in out
          and "引擎: 自动（优先 hashcat/GPU，失败自动改 john）" in out)
    check("向导 GPU=y 检测到 GTX 1650，走 auto（失败可回落 john）", ok, "rc=%d out=%s" % (rc, out))
    rc, out, _ = run_wizard(cfg_dir, answers, "0")
    ok = (rc == 2 and "未检测到可用 GPU" in out and "引擎: john (cpu)" in out)
    check("向导未检测到 GPU 时 engine=john(cpu) 且有提示", ok, "rc=%d out=%s" % (rc, out))


def test_rar3_modes():
    h1 = "$RAR3$*1*ad56eb40219c9da2*834064ce*32*13*1*eb47b1abe17a1a75bce6c92ab1cef3f4126035ea95deaf08b3f32a0c7b8078e1*33"
    h0 = "$RAR3$*0*ad56eb40219c9da2*834064ce*32*13*1*eb47b1abe17a1a75bce6c92ab1cef3f4126035ea95deaf08b3f32a0c7b8078e1*33"
    g1 = crumbs._guess_mode_from_sigil([h1], "rar4")
    g0 = crumbs._guess_mode_from_sigil([h0], "rar4")
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        mode, cands = crumbs.resolve_hashcat_mode(str(STUBS / "hashcat"), [h1], "rar4")
    ok = (g1 == "23800" and g0 == "12500" and mode == "23800"
          and cands == [23800] and "退回签名猜测" not in buf.getvalue())
    check("RAR3 identify 只给 [23800] 时选 23800 不 fallback，sigil *1*→23800、*0*→12500", ok,
          "g1=%s g0=%s mode=%s cands=%s stderr=%s" % (g1, g0, mode, cands, buf.getvalue()))


def main():
    tmp = Path(tempfile.mkdtemp(prefix="crumbs_gpu_test_"))
    try:
        test_select_engine_gpu_despite_cfg_false()
        test_forced_hashcat_cpu_warning()
        test_rar3_modes()
        test_crack_gpu_found(tmp)
        test_gpu_fail_auto_fallback(tmp)
        test_gpu_fail_forced_error(tmp)
        test_potfile_tempdir_cleanup(tmp)
        test_wizard_gpu_yes_and_no(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if FAILED:
        print("\n%d 项 FAIL" % FAILED)
        return 1
    print("\n[OK] 全部 GPU/hashcat 桩测试通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
