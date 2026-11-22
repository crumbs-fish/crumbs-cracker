#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 crumbs contributors
"""crumbs_cracker.py — 跨平台压缩包密码破解驱动脚本（仅 Python 标准库）。

职责：识别格式 -> 提取哈希 -> 选择引擎(hashcat/john) -> 破解 -> 7z/unrar 复核明文。
约定：
- 外部程序一律 subprocess 列表参数调用，绝不使用 shell 拼接；
- 文本读写与子进程输出一律 encoding='utf-8', errors='replace'；
- 路径一律 pathlib，项目根由 Path(__file__).resolve().parent 推导。
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

EXIT_FOUND = 0
EXIT_NOT_FOUND = 1
EXIT_ERROR = 2

MAGICS = [
    ("zip", b"PK\x03\x04"),
    ("zip", b"PK\x05\x06"),
    ("zip", b"PK\x07\x08"),
    ("7z", b"7z\xbc\xaf\x27\x1c"),
    ("rar5", b"Rar!\x1a\x07\x01\x00"),
    ("rar4", b"Rar!\x1a\x07\x00"),
]

HASH_SIGILS = ("$pkzip$", "$pkzip2$", "$zip2$", "$RAR3$", "$rar5$", "$7z$")
HASH_RE = re.compile(
    r"\$(?:pkzip2|zip2)\$.*?\$/(?:pkzip2|zip2)\$"
    r"|\$(?:pkzip|RAR3|rar5|7z)\$[^\s:]+"
)

ARCHIVE_HC_MODES = {13600, 17200, 17210, 17220, 17225, 17230, 11600, 12500, 13000, 23700, 23800}
FORMAT_DEFAULT_MODES = {"zip": "17200", "7z": "11600", "rar4": "12500", "rar5": "13000"}
FATAL_MARKERS = (
    "No hashes loaded",
    "Token length exception",
    "Separator unmatched",
    "Hash-file parse error",
)

HASHCAT_MEM_MARKERS = (
    "Not enough allocatable device memory",
    "Failed to create kernel compiler pass",
    "CL_OUT_OF_HOST_MEMORY",
    "clCreateBuffer",
    "No OpenCL devices found",
)

LEGACY_PKZIP_MODES = (17200, 17210, 17220, 17225)

_INVISIBLE_CHARS = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u200e\u200f"
                                              "\u202a\u202b\u202c\u202d\u202e"
                                              "\u2066\u2067\u2068\u2069\ufeff"))


def _strip_invisibles(text):
    """去掉拖拽路径里夹带的双向控制符/零宽字符（Windows 拖拽会带 U+202A 之类）。"""
    return str(text).translate(_INVISIBLE_CHARS)

ATTACK_HC = {"wordlist": "0", "mask": "3", "hybrid": "6"}


class AcrackError(Exception):
    """参数或环境错误，统一映射为退出码 2。"""


def configure_stdio():
    """Windows 控制台编码兜底：优先把 stdout/stderr 重配为 utf-8。"""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def _is_windows_abs(text):
    """把 C:\\path 或 \\\\server\\share 这类 Windows 绝对路径识别为绝对路径。"""
    return bool(re.match(r"^[A-Za-z]:[\\/]", text)) or text.startswith(("\\\\", "//"))


# ---------------------------------------------------------------- 终端界面
# 颜色只在交互终端里开；重定向到文件或设置 NO_COLOR 时退回纯文本。
# 图标在 UTF-8 终端里用，老式 CP936 控制台退回 ASCII，避免 UnicodeEncodeError。
_UI_STATE = {"checked": False, "color": False, "fancy": False}


def _ui_init():
    if _UI_STATE["checked"]:
        return _UI_STATE
    _UI_STATE["checked"] = True
    enc = (getattr(sys.stdout, "encoding", None) or "").lower()
    try:
        "\u2714\u2716\u25b8\u2500".encode(enc or "ascii", "strict")
        _UI_STATE["fancy"] = True
    except (LookupError, UnicodeEncodeError):
        _UI_STATE["fancy"] = False
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return _UI_STATE
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
                _UI_STATE["color"] = True
        except Exception:
            _UI_STATE["color"] = False
    else:
        _UI_STATE["color"] = True
    return _UI_STATE


def _paint(text, code):
    if not _ui_init()["color"]:
        return text
    return "\x1b[%sm%s\x1b[0m" % (code, text)


def _bold(t):
    return _paint(t, "1")


def _dim(t):
    return _paint(t, "2")


def _red(t):
    return _paint(t, "31")


def _green(t):
    return _paint(t, "32")


def _yellow(t):
    return _paint(t, "33")


def _cyan(t):
    return _paint(t, "36")


def _sym(name):
    table = {"ok": ("\u2714", "[OK]"), "bad": ("\u2716", "[x]"), "warn": ("\u26a0", "[!]"),
             "step": ("\u25b8", ">"), "bar": ("\u2500", "-")}
    return table[name][0 if _ui_init()["fancy"] else 1]


def _width(text):
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def ui_banner(title, subtitle=None):
    print("")
    print("  " + _cyan(_bold(title)))
    if subtitle:
        print("  " + _dim(subtitle))
    print("  " + _dim(_sym("bar") * max(_width(title) + 2, 56)))
    print("")


def ui_section(title):
    print("")
    print("  " + _cyan(_sym("step") + " " + _bold(title)))


def ui_headline(tone, text):
    color = {"ok": _green, "bad": _red, "warn": _yellow}.get(tone, _cyan)
    icon = {"ok": _sym("ok"), "bad": _sym("bad"), "warn": _sym("warn")}.get(tone, _sym("step"))
    print("")
    print("  " + color(_bold(icon + " " + text)))
    print("  " + _dim(_sym("bar") * 58))


def ui_table(rows):
    width = max([_width(str(k)) for k, _ in rows] + [6])
    for key, value in rows:
        key = str(key)
        print("  " + _dim(key + " " * (width - _width(key))) + "   " + str(value))
    print("")


def ui_info(text):
    print("  " + _dim(text))


def ui_ok(text):
    print("  " + _green(_sym("ok") + " " + text))


def ui_warn(text):
    print("  " + _yellow(_sym("warn") + " " + text), file=sys.stderr)


def ui_err(text):
    print("  " + _red(_sym("bad") + " " + text), file=sys.stderr)


def ui_progress(index, total, label, mask=None):
    head = _cyan("[%d/%d]" % (index, total))
    tail = "  " + _dim("掩码 " + mask) if mask else ""
    print("  %s %s%s" % (head, label, tail), file=sys.stderr)


def detect_format(archive):
    """按文件头魔术字节识别格式；扩展名只作辅助提示。"""
    try:
        with archive.open("rb") as fh:
            head = fh.read(8)
    except OSError as exc:
        raise AcrackError("无法读取文件 %s: %s" % (archive, exc))
    for fmt, magic in MAGICS:
        if head.startswith(magic):
            return fmt
    return None


def read_engines(explicit=None):
    """读取 engines.json：--engines 优先，其次项目 engines/engines.json，再其次环境变量。"""
    candidates = []
    if explicit is not None:
        candidates.append(Path(str(explicit)).expanduser())
    else:
        default = PROJECT_ROOT / "engines" / "engines.json"
        if default.is_file():
            candidates.append(default)
        env = os.environ.get("CRUMBS_ENGINES_JSON")
        if env:
            candidates.append(Path(env).expanduser())
    for cfg_path in candidates:
        if not cfg_path.is_file():
            raise AcrackError("engines.json 不存在: %s" % cfg_path)
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AcrackError("读取引擎配置失败 %s: %s" % (cfg_path, exc))
        if not isinstance(data, dict):
            raise AcrackError("引擎配置必须是 JSON 对象: %s" % cfg_path)
        return data, cfg_path.parent
    return {}, None


def resolve_tool(cfg, cfg_dir, key, path_names):
    """解析单个工具路径：json 键优先（相对路径基于 json 目录），否则 PATH 兜底。"""
    value = cfg.get(key)
    if value not in (None, ""):
        text = str(value)
        if os.sep not in text and "/" not in text and "\\" not in text:
            found = shutil.which(text)
            if found:
                return found
        cand = Path(text).expanduser()
        if not cand.is_absolute() and not _is_windows_abs(text):
            cand = cfg_dir / cand
        if not cand.exists():
            raise AcrackError("engines.json 键 %s 指向不存在的文件: %s" % (key, cand))
        return str(cand)
    for name in path_names:
        found = shutil.which(name)
        if found:
            return found
    return None


def resolve_perl(cfg, cfg_dir):
    """perl_bin 允许是命令名或路径；缺省回退 PATH 上的 perl。"""
    value = cfg.get("perl_bin")
    if value not in (None, ""):
        text = str(value)
        found = shutil.which(text)
        if found:
            return found
        cand = Path(text).expanduser()
        if not cand.is_absolute() and not _is_windows_abs(text):
            cand = cfg_dir / cand
        if cand.exists():
            return str(cand)
        raise AcrackError("engines.json 键 perl_bin 指向不存在的文件: %s" % cand)
    return shutil.which("perl")


def resolve_tools(cfg, cfg_dir):
    return {
        "hashcat": resolve_tool(cfg, cfg_dir, "hashcat_bin", ["hashcat"]),
        "john": resolve_tool(cfg, cfg_dir, "john_bin", ["john"]),
        "zip2john": resolve_tool(cfg, cfg_dir, "zip2john", ["zip2john"]),
        "rar2john": resolve_tool(cfg, cfg_dir, "rar2john", ["rar2john"]),
        "sevenz2john": resolve_tool(cfg, cfg_dir, "sevenz2john", ["7z2john.pl", "7z2john"]),
        "unrar": resolve_tool(cfg, cfg_dir, "unrar_bin", ["unrar"]),
        "rar": resolve_tool(cfg, cfg_dir, "rar_bin", ["rar"]),
        "sevenz": resolve_tool(cfg, cfg_dir, "sevenz_bin", ["7z", "7zz"]),
        "perl": resolve_perl(cfg, cfg_dir),
    }


def _terminate_process(proc):
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
    except OSError:
        return
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
            proc.wait(timeout=3)
        except OSError:
            pass


def run_cmd(cmd, cwd=None, stdin_text=None, stdin_path=None):
    """列表参数运行外部程序；stdin_text 非空时喂入子进程 stdin，stdin_path 非空时用文件句柄重定向；Ctrl+C 时 terminate/kill。"""
    argv = [str(c) for c in cmd]
    stdin_fh = open(stdin_path, "rb") if stdin_path is not None else None
    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            stdin=stdin_fh if stdin_fh is not None else (subprocess.PIPE if stdin_text is not None else None),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            out, err = proc.communicate(stdin_text)
        except KeyboardInterrupt:
            _terminate_process(proc)
            raise
        return subprocess.CompletedProcess(argv, proc.returncode, out or "", err or "")
    finally:
        if stdin_fh is not None:
            stdin_fh.close()


def build_extract_cmd(tool, archive, perl_bin):
    """7z 提取器是 .pl 脚本时必须用 perl 运行；其余直接执行。"""
    if str(tool).lower().endswith(".pl"):
        if not perl_bin:
            raise AcrackError(
                "7z 提取器是 perl 脚本，但未找到 perl（engines.json 的 perl_bin 或 PATH 中安装 perl）"
            )
        return [perl_bin, tool, str(archive)]
    return [tool, str(archive)]


def extract_hashes(extract_cmd):
    proc = run_cmd(extract_cmd)
    text = "%s\n%s" % (proc.stdout or "", proc.stderr or "")
    hashes = HASH_RE.findall(text)
    if not hashes:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise AcrackError("提取器未输出可识别哈希 (%s): %s" % (extract_cmd[0], detail[:300]))
    seen = set()
    ordered = []
    for h in hashes:
        if h not in seen:
            seen.add(h)
            ordered.append(h)
    return ordered


_GPU_PROBE_CACHE = {}


def _hashcat_cwd(hashcat_bin):
    """hashcat 必须以自身安装目录为 cwd 运行（Windows/Linux 都如此）。"""
    try:
        parent = Path(str(hashcat_bin)).resolve().parent
    except (OSError, ValueError):
        parent = Path(".")
    return str(parent) if str(parent) else "."


def probe_gpu(hashcat_bin):
    """运行 hashcat -I 探测 GPU；同一 hashcat 路径进程内只探测一次。

    返回 {"available": bool, "devices": [设备名...], "raw": 前 40 行 -I 输出}；
    任何异常（不可执行/超时等）都返回 available=False 而不抛错。
    """
    if not hashcat_bin:
        return {"available": False, "devices": [], "raw": ""}
    key = str(hashcat_bin)
    if key in _GPU_PROBE_CACHE:
        return _GPU_PROBE_CACHE[key]
    try:
        proc = subprocess.run(
            [str(hashcat_bin), "-I"],
            cwd=_hashcat_cwd(hashcat_bin),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        result = {"available": False, "devices": [], "raw": ""}
        _GPU_PROBE_CACHE[key] = result
        return result
    raw = "%s\n%s" % (proc.stdout or "", proc.stderr or "")
    devices = []
    is_gpu = False
    for line in raw.splitlines():
        m = re.match(r"^\s*Type\b.*?[:.]\s*(GPU|CPU)\b", line, flags=re.I)
        if m:
            is_gpu = m.group(1).upper() == "GPU"
            continue
        m = re.match(r"^\s*Name\b[^:]*:\s*(.+?)\s*$", line, flags=re.I)
        if m and is_gpu:
            devices.append(m.group(1).strip())
            is_gpu = False
    result = {"available": bool(devices), "devices": devices,
              "raw": "\n".join(raw.splitlines()[:40])}
    _GPU_PROBE_CACHE[key] = result
    return result


def _probe_saw_device_type(probe):
    """probe 的 -I 输出里出现过 Type: GPU/CPU 行，说明探测命令本身成功执行了。"""
    return bool(re.search(r"^\s*Type\b.*?[:.]\s*(GPU|CPU)\b",
                          probe.get("raw", ""), flags=re.I | re.M))


def detect_backend(hashcat_bin):
    """运行 hashcat -I 解析后端；保留旧接口，探测失败时返回 cpu。"""
    probe = probe_gpu(hashcat_bin)
    return "gpu" if probe["available"] else "cpu"


def _guess_mode_from_sigil(hashes, fmt):
    """hashcat --identify 不可用时的退回猜测：$zip2$ 必须是 13600。"""
    h = hashes[0] if hashes else ""
    if h.startswith("$zip2$"):
        return "13600"
    if h.startswith("$pkzip$"):
        return "17200"
    if h.startswith("$pkzip2$"):
        m = re.match(r"\$pkzip2\$(\d+)\*", h)
        if m:
            count = int(m.group(1))
            if count == 1:
                parts = h.split("*")
                method = parts[2] if len(parts) > 2 else ""
                return "17210" if method == "0" else "17200"
            return "17220"
    if h.startswith("$RAR3$"):
        if h.startswith("$RAR3$*1*"):
            return "23800"
        return "12500"
    if h.startswith("$rar5$"):
        return "13000"
    if h.startswith("$7z$"):
        return "11600"
    return FORMAT_DEFAULT_MODES.get(fmt, "0")


def resolve_hashcat_mode(hashcat_bin, hashes, fmt, allowed=None):
    """用 hashcat --identify 解析压缩包族模式；不可用时退回签名猜测并打印警告。

    allowed 非空时先把候选限定到该集合（legacy $pkzip$ 强制 hashcat 用）。
    """
    candidates = []
    try:
        fd, name = tempfile.mkstemp(prefix="crumbs_id_", suffix=".txt")
        os.close(fd)
        tmp = Path(name)
        try:
            tmp.write_text("\n".join(hashes) + "\n", encoding="utf-8", errors="replace")
            proc = run_cmd([hashcat_bin, "--identify", str(tmp)], cwd=_hashcat_cwd(hashcat_bin))
            text = "%s\n%s" % (proc.stdout or "", proc.stderr or "")
            candidates = [int(x) for x in re.findall(r"^\s*(\d+)\s*\|", text, flags=re.M)]
        finally:
            tmp.unlink(missing_ok=True)
    except OSError:
        candidates = []
    if allowed is not None:
        candidates = [x for x in candidates if x in allowed]
    for mode in candidates:
        if mode in ARCHIVE_HC_MODES:
            return str(mode), [mode]
    guess = _guess_mode_from_sigil(hashes, fmt)
    print("警告: hashcat --identify 未给出可用压缩包族模式（候选 %s），退回签名猜测 %s" % (candidates, guess),
          file=sys.stderr)
    return guess, candidates


def _check_zip_encrypted(archive):
    """未加密 zip 会让任何候选通过复核，必须先拒绝。

    逐个条目判断：目录条目和「先加目录再加密文件」的包（如某些 zip 工具）
    第一个条目是 flag=0 的目录，只看 infos[0] 会误判成未加密。
    """
    try:
        with zipfile.ZipFile(str(archive)) as zf:
            infos = zf.infolist()
            if not infos:
                raise AcrackError("zip 内没有任何条目，无法破解")
            files = [i for i in infos if not i.is_dir()]
            pool = files or infos
            enc = [i for i in pool if (i.flag_bits & 0x1) or i.compress_type == 99]
            if not enc:
                raise AcrackError("该压缩包未加密，无需破解")
    except AcrackError:
        raise
    except Exception as exc:
        raise AcrackError("无法解析 zip 结构: %s" % exc)


def _proc_text(proc):
    return "%s\n%s" % (proc.stdout or "", proc.stderr or "")


def _match_fatal_marker(proc, markers):
    text = _proc_text(proc)
    for marker in markers:
        if marker in text:
            return marker
    return None


def _last_output_lines(proc, n=3):
    text = _proc_text(proc)
    lines = [line for line in text.splitlines() if line.strip()]
    return "\n".join(lines[-n:]) if lines else text[-300:]


def check_crack_result(proc, engine):
    """引擎退出码/输出错误检查：错误退出或致命标记 -> 报错而不是假 NOT FOUND。"""
    if "Integer overflow detected in keyspace" in _proc_text(proc):
        raise AcrackError("掩码组合数超出 hashcat 可表示范围（2^64），请缩短长度或缩小字符集")
    marker = _match_fatal_marker(proc, FATAL_MARKERS + HASHCAT_MEM_MARKERS)
    if marker:
        if engine == "hashcat":
            raise AcrackError("hashcat 运行失败：输出包含致命错误 '%s'，最后输出:\n%s"
                              % (marker, _last_output_lines(proc)))
        raise AcrackError("%s 输出包含致命错误 '%s'，最后输出: %s" % (engine, marker, _proc_text(proc)[-500:]))
    if proc.returncode not in (0, 1):
        if engine == "hashcat":
            raise AcrackError("hashcat 运行失败：退出码 %s（错误），最后输出:\n%s"
                              % (proc.returncode, _last_output_lines(proc)))
        raise AcrackError("%s 退出码 %s（错误），最后输出: %s" % (engine, proc.returncode, _proc_text(proc)[-500:]))


def _pick_verify_tool(fmt, tools):
    if fmt in ("zip", "7z"):
        return tools.get("sevenz") or "7z", "7z"
    tool = tools.get("unrar") or tools.get("rar")
    if tool:
        return tool, "unrar" if tools.get("unrar") else "rar"
    tool = tools.get("sevenz")
    if tool:
        return tool, "7z"
    return "unrar", "unrar"


def _hashcat_backend(hashcat_bin, cfg, probe_backend):
    """运行时探测优先：探测到 GPU -> gpu；明确只有 CPU -> cpu；
    探测失败（不可执行/超时）才退回 engines.json 的 gpu_available 提示值。
    """
    if probe_backend and hashcat_bin:
        probe = probe_gpu(hashcat_bin)
        if probe["available"]:
            return "gpu"
        if _probe_saw_device_type(probe):
            return "cpu"
    gpu_avail = cfg.get("gpu_available")
    return "gpu" if isinstance(gpu_avail, bool) and gpu_avail else "cpu"


def select_engine(tools, cfg, forced, probe_backend):
    """返回 (engine, backend, warning)。

    auto 顺序：探测到 GPU -> hashcat(gpu)；否则有 john -> john(cpu)；
    否则有 hashcat -> hashcat(cpu，附 warning)。--engine hashcat 强制时无 GPU 也
    返回 hashcat(cpu) 并附 warning。
    """
    if forced == "hashcat":
        if not tools.get("hashcat"):
            raise AcrackError("--engine hashcat 但未找到 hashcat（PATH 或 engines.json 的 hashcat_bin）")
        backend = _hashcat_backend(tools["hashcat"], cfg, probe_backend)
        warning = None if backend == "gpu" else "未检测到 GPU，hashcat 将以 CPU 运行（可能极慢）"
        return "hashcat", backend, warning
    if forced == "john":
        if not tools.get("john"):
            raise AcrackError("--engine john 但未找到 john（PATH 或 engines.json 的 john_bin）")
        return "john", "cpu", None
    hashcat = tools.get("hashcat")
    if hashcat:
        backend = _hashcat_backend(hashcat, cfg, probe_backend)
        if backend == "gpu":
            return "hashcat", "gpu", None
        if tools.get("john"):
            return "john", "cpu", None
        return "hashcat", "cpu", "未检测到可用 GPU 且未找到 john，hashcat 以 CPU 回退运行"
    if tools.get("john"):
        if isinstance(cfg.get("gpu_available"), bool) and cfg.get("gpu_available"):
            return "john", "cpu", "检测到 GPU 但未找到 hashcat，已使用 john（CPU）"
        return "john", "cpu", None
    return None, None, None


def extractor_for_format(tools, fmt):
    if fmt == "zip":
        key, label = "zip2john", "zip2john"
    elif fmt == "7z":
        key, label = "sevenz2john", "7z2john.pl"
    else:
        key, label = "rar2john", "rar2john"
    tool = tools.get(key)
    if not tool:
        raise AcrackError(
            "找不到 %s（格式 %s）：请安装 john-jumbo 提取器，或用 --engines 指定 engines.json" % (label, fmt)
        )
    return tool, label


def _add_common(parser):
    parser.add_argument("--engine", choices=["auto", "hashcat", "john"], default="auto",
                        help="强制引擎：auto / hashcat / john（默认 auto）")
    parser.add_argument("--engines", type=Path, help="指定 engines.json 路径（优先级最高）")
    parser.add_argument("--json", action="store_true", help="输出结构化 JSON")


HELP_TEXT = "显示本帮助并退出"

USAGE_MAIN = """\
常用用法（示例里的 压缩包.zip 换成真实文件；Windows 下把 ./crumbs-cracker.sh 换成 crumbs-cracker.bat）
  0) 交互式：把压缩包拖到 crumbs-cracker.bat / crumbs-cracker.sh 上，或者 crumbs-cracker.bat 压缩包.zip
       依次询问 破解方式 -> 字典位置 -> 密码长度 -> 包含字符 -> 是否尝试 GPU（需 NVIDIA/AMD 驱动 + hashcat）
        密码长度那一问输 0 = 不知道长度，接着问起始位与结束位，从短到长逐位试
        混合模式的长度是「后缀位数」，例如 secret + 2 位数字 就是 2
       不想问答就直接用下面 2/3/4 条
  1) 只看格式和将用哪个引擎，不破解
       ./crumbs-cracker.sh check 压缩包.zip
  2) 字典攻击（最常用）
       ./crumbs-cracker.sh crack -a wordlist -w 字典.txt 压缩包.zip
       包内自带字典（可直接用，无需另下）：
         dicts/common.txt       10001 条通用弱口令（首选，几秒跑完）
         dicts/common-100k.txt  100000 条，命中率更高、耗时约 10 倍
       ./crumbs-cracker.sh crack -a wordlist -w dicts/common.txt 压缩包.zip
   不写 -w 时（wordlist / hybrid）自动使用包内 dicts/common.txt
  3) 纯暴力（掩码攻击，不需要字典）
       ./crumbs-cracker.sh crack -a mask -m '?d?d?d?d' 压缩包.7z
  4) 词表加后缀（hybrid）
       ./crumbs-cracker.sh crack -a hybrid -w 字典.txt -m '?d?d' 压缩包.rar
  5) 不知道密码长度（逐位尝试，前一位没出来才试下一位）
       ./crumbs-cracker.sh crack -a mask -m '?d' --len-min 1 --len-max 6 压缩包.zip
       ./crumbs-cracker.sh crack -a hybrid -w 字典.txt -m '?d' --len-min 1 --len-max 4 压缩包.rar
  6) 只打印将执行的命令，不真跑
       ./crumbs-cracker.sh crack -a wordlist -w 字典.txt --dry-run 压缩包.zip
  7) 机器可读输出，供脚本解析
       ./crumbs-cracker.sh crack -a wordlist -w 字典.txt --json 压缩包.zip

掩码字符集（-a mask 与 -a hybrid 的 -m 参数）
  ?d 数字 0-9   ?l 小写 a-z   ?u 大写 A-Z   ?s 符号   ?a 所有可打印字符   ?b 全部 256 字节
  普通字符按字面处理：-m 'pass?d?d' 表示 pass00 到 pass99
  不知道长度：-m 只写一位的单元，用 --len-min/--len-max 逐位尝试
        -m '?d' --len-min 1 --len-max 6   先试 1 位，没出来再 2 位……直到 6 位
        混合同理：-a hybrid -m '?d' --len-min 1 --len-max 4

组合数上限：单次攻击最多约 1.8e19 种（2^64），超出会直接报错而不是白跑
  逐位尝试是按"每一位"单独比的：某一位超限就从那一位起不再尝试，前面的位数照常跑
    （例：?a 的 1-12 位 → 实际只跑 1-9 位，因为 95^10≈6e19 已超上限）
  单轮攻击（不给长度）超限才整单报错：?a 的 10 位 = 95^10≈6e19
  后缀/长度别贪大：先试 4-6 位，或缩小字符集（例如只用 ?d?l）

纯暴力掩码示例（配合上面的实测速度估算耗时）
  4 位数字        -m '?d?d?d?d'
  6 位小写        -m '?l?l?l?l?l?l'
  8 位全字符      -m '?a?a?a?a?a?a?a?a'

GPU 加速（hashcat）
  需要 NVIDIA/AMD 驱动 + hashcat 可用；auto 检测到 GPU 才走 hashcat(gpu)，否则 john(cpu)。
  --engine hashcat 可强制：未检测到 GPU 时以 CPU 运行（可能极慢）。
  支持模式：13600 zip AES、17200/17210/17220/17225 zip ZipCrypto、
           11600 7z、12500/23700/23800 rar4、13000 rar5
  实测速度（RTX 4060 + hashcat，仅破解阶段）：
    13600 zip AES ≈ 2930 kH/s；11600 7z ≈ 510 kH/s
    13000 rar5 ≈ 48.2 kH/s；23800 rar4 ≈ 30.7 kH/s
  CPU（john，2 核）对照：zip AES 54 kH/s、7z 51.8 H/s、rar5 837 H/s、rar4 135 H/s
  提醒：7z 即使有 GPU 也慢（比 zip AES 慢约 5700 倍），掩码空间大时先想别的思路

实测速度（本机 2 核 CPU、john 引擎，含提取与复核开销）
  zip ZipCrypto  54 kH/s；4 位数字瞬间完成
  zip AES        4 位数字 约 1 秒；6 位小写 约 100 分钟
  7z             51.8 H/s；4 位数字 约 2 分钟；6 位小写 约 1 个月（基本不可行）
  rar4           4 位数字 约 1 分钟
  rar5           837 H/s；4 位数字 约 2 秒

把压缩包拖进窗口时路径两侧可能夹带不可见控制符，已自动清理，直接粘贴即可
legacy $pkzip$（老 zip）auto 会先试 GPU，hashcat 报结构性错误才自动改用 john

退出码：0 找到密码 / 1 没找到 / 2 参数或环境错误
支持格式：zip（ZipCrypto / AES-256 / 多条目）、7z（含加密文件名）、rar4、rar5
"""

USAGE_CHECK = """\
说明
  check 只做三件事：读魔术字节判格式 -> 用 *2john 提取哈希 -> 报告将用哪个引擎与后端。
  不破解、不改动压缩包；加 --json 便于脚本判断。

示例
  ./crumbs-cracker.sh check 压缩包.zip
  ./crumbs-cracker.sh check 压缩包.7z
  ./crumbs-cracker.sh check 压缩包.rar --json

退出码：0 识别并提取成功（不代表已加密）/ 2 无法识别或提取失败
"""

USAGE_CRACK = """\
攻击模式
  -a wordlist   字典攻击：      -w 字典.txt
  -a mask       纯暴力/掩码：   -m '?d?d?d?d'
  -a hybrid     字典 + 掩码后缀：-w 字典.txt -m '?d?d'

不知道长度时（mask / hybrid 都支持）
  -m 只写「一位/一个单元」，再给 --len-min 与 --len-max，从短到长逐位尝试
  ./crumbs-cracker.sh crack -a mask   -m '?d' --len-min 1 --len-max 6 压缩包.zip
  ./crumbs-cracker.sh crack -a hybrid -w 字典.txt -m '?d' --len-min 1 --len-max 4 压缩包.rar
  每位都完整跑完才进入下一位；命中即停止，并打印「本轮掩码长度」

掩码字符集
  ?d 数字 0-9   ?l 小写 a-z   ?u 大写 A-Z   ?s 符号   ?a 所有可打印字符   ?b 全部 256 字节
  普通字符按字面处理：-m 'pass?d?d' 表示 pass00 到 pass99
  自定义集合：-1 '?d?l' -m '?1?1?1?1'（?1 处为数字或小写字母，4 位）

GPU 加速
  需要 NVIDIA/AMD 驱动 + hashcat 可用；auto 检测到 GPU 用 hashcat(gpu)，否则 john(cpu)。
  支持模式：13600 zip AES、17200/17210/17220/17225 zip ZipCrypto、11600 7z、12500 rar4、13000 rar5。
  7z / rar4 即使有 GPU 也很慢。

组合数上限
  单次攻击最多约 1.8e19 种（2^64）。逐位尝试按单个长度分别比：撑得住就继续下一位，
  撑不住就停（?a 的 1-12 位实际只跑 1-9 位）；单轮攻击超限才整单报错。

纯暴力常用掩码
  4 位数字        -m '?d?d?d?d'
  6 位小写        -m '?l?l?l?l?l?l'
  8 位全字符      -m '?a?a?a?a?a?a?a?a'
  固定前缀 + 数字  -m 'admin?d?d'

示例
  ./crumbs-cracker.sh crack -a wordlist -w 字典.txt 压缩包.zip
  ./crumbs-cracker.sh crack -a mask -m '?d?d?d?d' 压缩包.7z
  ./crumbs-cracker.sh crack -a hybrid -w 字典.txt -m '?d?d' 压缩包.rar
  ./crumbs-cracker.sh crack -a wordlist -w 字典.txt --dry-run 压缩包.zip
  ./crumbs-cracker.sh crack -a wordlist -w 字典.txt --json 压缩包.zip

输出字段（不加 --json 时）
  已找到密码: <明文>（不知道长度时另有一行「本轮掩码长度」）  或    未找到密码（另有「尝试长度」）
  引擎: john (cpu) / hashcat (gpu)
  攻击模式 / 耗时 / 复核方式（7z、unrar、zipfile、rar）/ 警告

退出码：0 找到密码 / 1 没找到 / 2 参数或环境错误
"""

_ARG_ERR_PATTERNS = [
    (r"the following arguments are required: (.+)", "缺少必需参数: %s"),
    (r"unrecognized arguments: (.+)", "无法识别的参数: %s"),
    (r"argument (.+?): invalid choice: (.+?) \(choose from (.+)\)$", "参数 %s 取值无效 %s（可选: %s）"),
    (r"argument (.+?): expected one argument", "参数 %s 需要一个值"),
    (r"argument (.+?): invalid .+ value: (.+)", "参数 %s 的值无效: %s"),
]


def _zh_arg_error(message):
    for pattern, tmpl in _ARG_ERR_PATTERNS:
        m = re.match(pattern, message)
        if m:
            return tmpl % m.groups()
    return message


class ZhArgumentParser(argparse.ArgumentParser):
    """argparse 的 usage/报错信息本地化。"""

    def format_usage(self):
        return super().format_usage().replace("usage: ", "用法: ", 1)

    def format_help(self):
        return super().format_help().replace("usage: ", "用法: ", 1)

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(EXIT_ERROR, "%s: 错误: %s\n" % (self.prog, _zh_arg_error(message)))


def _add_help(parser):
    parser.add_argument("-h", "--help", action="help", help=HELP_TEXT)
    parser._positionals.title = "位置参数"
    parser._optionals.title = "选项"


def build_parser():
    parser = ZhArgumentParser(
        prog="crumbs_cracker.py",
        add_help=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="跨平台压缩包密码破解驱动：识别格式、提取哈希、调用 hashcat/john、复核明文。",
        epilog=USAGE_MAIN,
    )
    _add_help(parser)
    sub = parser.add_subparsers(dest="command", required=True, title="子命令",
                                parser_class=ZhArgumentParser)

    p_check = sub.add_parser("check", add_help=False, help="识别格式 + 提取哈希 + 报告将使用的引擎（不破解）",
                             formatter_class=argparse.RawDescriptionHelpFormatter, epilog=USAGE_CHECK)
    _add_help(p_check)
    p_check.add_argument("archive", type=Path, help="压缩包路径")
    _add_common(p_check)

    p_crack = sub.add_parser("crack", add_help=False, help="破解压缩包密码",
                             formatter_class=argparse.RawDescriptionHelpFormatter, epilog=USAGE_CRACK)
    _add_help(p_crack)
    p_crack.add_argument("archive", type=Path, help="压缩包路径")
    p_crack.add_argument("-a", "--attack", choices=["wordlist", "mask", "hybrid"], required=True,
                         help="攻击模式：wordlist / mask / hybrid")
    p_crack.add_argument("-w", "--wordlist", type=Path, help="字典文件（wordlist / hybrid 需要）")
    p_crack.add_argument("-m", "--mask", help="掩码，如 ?d?d?d?d（mask / hybrid 需要）")
    p_crack.add_argument("-1", "--charset1",
                         help="自定义字符集 1，掩码里用 ?1 引用，如 -1 '?d?l' -m '?1?1?1'")
    p_crack.add_argument("--len-min", type=int, metavar="N",
                         help="逐位尝试的起始长度：-m 只写单元（如 '?d'），从 N 位开始，配合 --len-max 使用")
    p_crack.add_argument("--len-max", type=int, metavar="N", help="逐位尝试的结束长度（含）")
    p_crack.add_argument("--dry-run", action="store_true", help="只打印将执行的破解/复核命令（会先运行提取器与 hashcat --identify 确定模式）")
    _add_common(p_crack)
    return parser


def run_check(args):
    fmt = detect_format(args.archive)
    if fmt is None:
        raise AcrackError(
            "无法识别的压缩格式: %s（扩展名 %s 仅作辅助，不参与判定）" % (args.archive, args.archive.suffix or "无")
        )
    cfg, cfg_dir = read_engines(args.engines)
    tools = resolve_tools(cfg, cfg_dir)
    extractor, _ = extractor_for_format(tools, fmt)
    extract_cmd = build_extract_cmd(extractor, args.archive, tools.get("perl"))
    hashes = extract_hashes(extract_cmd)
    engine, backend, engine_warning = select_engine(tools, cfg, args.engine, probe_backend=True)
    if engine is None:
        raise AcrackError("未找到可用引擎（hashcat 或 john）：请安装，或用 --engines 指定 engines.json")
    hashcat_mode = None
    mode_candidates = []
    if engine == "hashcat":
        allowed = LEGACY_PKZIP_MODES if hashes and hashes[0].startswith("$pkzip$") else None
        hashcat_mode, mode_candidates = resolve_hashcat_mode(tools["hashcat"], hashes, fmt, allowed=allowed)
    if args.json:
        print(json.dumps({
            "format": fmt,
            "hashes": hashes,
            "hash_count": len(hashes),
            "engine": engine,
            "backend": backend,
            "warning": engine_warning,
            "hashcat_mode": hashcat_mode,
            "mode_candidates": mode_candidates,
            "extractor": extractor,
        }, ensure_ascii=False))
    else:
        ui_headline("ok", "压缩包已解析: %s" % args.archive.name)
        ui_table([
            ("格式", fmt),
            ("哈希条目数", len(hashes)),
            ("引擎", engine or "无"),
            ("后端", backend or "无"),
            ("hashcat 模式", hashcat_mode or "无"),
            ("模式候选", ", ".join(str(c) for c in mode_candidates) or "无"),
        ])
        for h in hashes:
            print("  " + _dim(str(h)))
        print("")
        if engine_warning:
            ui_warn(engine_warning)
    return EXIT_FOUND


def _default_wordlist():
    for cand in (Path("dicts/common.txt"), PROJECT_ROOT / "dicts" / "common.txt",
                 Path("samples/words.txt"), PROJECT_ROOT / "samples" / "words.txt"):
        if cand.is_file():
            return cand
    return None


def _validate_attack_args(args):
    if args.attack in ("wordlist", "hybrid") and args.wordlist is None:
        wl = _default_wordlist()
        if wl is None:
            raise AcrackError("-a %s 需要 -w/--wordlist <字典文件>（包内 dicts/common.txt 缺失）" % args.attack)
        print("提示: 未指定 -w，使用包内默认字典 %s" % wl, file=sys.stderr)
        args.wordlist = wl
    lo = getattr(args, "len_min", None)
    hi = getattr(args, "len_max", None)
    if lo is not None or hi is not None:
        if args.attack not in ("mask", "hybrid"):
            raise AcrackError("--len-min/--len-max 只用于 -a mask 与 -a hybrid")
        if lo is None or hi is None:
            raise AcrackError("--len-min 与 --len-max 需要同时给出（例如 --len-min 1 --len-max 6）")
        if not (1 <= lo <= hi <= 16):
            raise AcrackError("--len-min/--len-max 需满足 1 <= 起始长度 <= 结束长度 <= 16")
    if args.attack == "mask" and args.mask is None:
        raise AcrackError("-a mask 需要 -m/--mask '<掩码>'")
    if args.attack == "hybrid" and args.mask is None:
        raise AcrackError("-a hybrid 需要 -m/--mask '<掩码>'（只写后缀，例如 '?d?d'）")
    if args.attack in ("mask", "hybrid"):
        what = "后缀长度" if args.attack == "hybrid" else "密码长度"
        lens = _mask_lengths(args)
        if lens is None:
            worst = _keyspace_worst(args)
            if worst > _HC_KEYSPACE_LIMIT:
                raise AcrackError(
                    "组合数过大：本次约 %.3g 种，超出 hashcat 单次可枚举上限 2^64≈1.8e19；"
                    "请缩短%s或缩小字符集（例如先试 4-6 位），也可改用字典或分几次跑"
                    % (worst, what))
        else:
            # 逐位尝试是一轮一次调用，所以按"单个长度"分别比上限：
            # 撑得住就继续下一位，撑不住的那一位起（更长的只会更大）直接不试。
            first_bad = None
            for n in lens:
                if _keyspace_one(args, n) > _HC_KEYSPACE_LIMIT:
                    first_bad = n
                    break
            if first_bad == lens[0]:
                raise AcrackError(
                    "组合数过大：%d 位单轮就约 %.3g 种，超出 hashcat 单次可枚举上限 2^64≈1.8e19；"
                    "请缩小字符集或改用字典"
                    % (first_bad, _keyspace_one(args, first_bad)))
            if first_bad is not None:
                args.len_max = first_bad - 1
                print("提示: %d 位起的组合数超出 hashcat 单次上限 2^64≈1.8e19，"
                      "本次只逐位尝试 %d-%d 位（更长的%s请缩小字符集或改用字典）"
                      % (first_bad, lens[0], args.len_max, what), file=sys.stderr)
        worst = _keyspace_worst(args)
        if worst >= 10 ** 13:
            print("提示: 单轮组合数约 %.3g 种，即使有 GPU 也要很久，可先跑字典或缩小字符集"
                  % worst, file=sys.stderr)


def _hashcat_cmd(tool, mode, args, backend, hashfile, potfile, outfile):
    """生成完整 hashcat 命令；potfile/outfile 由调用方放在每次独立的临时目录。"""
    attack = ATTACK_HC[args.attack]
    cmd = [tool, "-m", mode, "-a", attack,
           "--potfile-path", str(potfile),
           "-o", str(outfile),
           "--outfile-format=2",
           "--status", "--status-timer=10",
           "--session", "crumbs"]
    if args.attack == "wordlist":
        tail = [str(hashfile), str(args.wordlist.resolve())]
    else:
        tail = []
        if getattr(args, "charset1", None):
            tail += ["-1", args.charset1]
        if args.attack == "mask":
            tail += [str(hashfile), args.mask]
        else:
            tail += [str(hashfile), str(args.wordlist.resolve()), args.mask]
    return cmd + tail


def _john_cmd(tool, args, hashfile, potfile):
    extra = ["-1=%s" % args.charset1] if getattr(args, "charset1", None) else []
    if args.attack == "wordlist":
        return [tool, "--wordlist=%s" % args.wordlist.resolve(), *extra, "--pot=%s" % potfile, str(hashfile)]
    if args.attack == "hybrid":
        suffix = args.mask
        if suffix.startswith("?w"):
            suffix = suffix[2:]
            print("提示: -m 只写后缀，前导 ?w 已自动去掉（实际掩码 ?w%s）" % suffix, file=sys.stderr)
        return [tool, "--stdin", "--mask=?w%s" % suffix, *extra, "--pot=%s" % potfile, str(hashfile)]
    return [tool, "--mask=%s" % args.mask, *extra, "--pot=%s" % potfile, str(hashfile)]


def _john_stdin_path(args):
    if args.attack != "hybrid":
        return None
    return str(args.wordlist.resolve())


def parse_john_show(stdout):
    """john --show 输出为 <来源文件>:<明文>；按最后一个冒号切分，跳过统计行与空明文。"""
    out = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        left, pw = line.rsplit(":", 1)
        pw = pw.strip()
        left = left.strip()
        if not pw or not left:
            continue
        if pw not in out:
            out.append(pw)
    return out


def _read_lines(path):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def _hex_decode_password(pw):
    if pw.startswith("$HEX[") and pw.endswith("]"):
        try:
            return bytes.fromhex(pw[5:-1]).decode("utf-8", errors="replace")
        except (ValueError, TypeError):
            return pw
    return pw


def _parse_hashcat_lines(paths):
    """逐行解析 hashcat outfile/potfile：兼容 hash:plain 与纯明文两种形式。"""
    candidates = []
    for path in paths:
        for line in _read_lines(path):
            pw = line.rsplit(":", 1)[1] if ":" in line else line
            pw = pw.strip()
            if not pw:
                continue
            pw = _hex_decode_password(pw)
            if pw not in candidates:
                candidates.append(pw)
    return candidates


def _extract_hashcat_password(outfile, potfile):
    """先读 outfile（--outfile-format=2 只写明文），为空再读 potfile；都为空 = 未找到。"""
    return _parse_hashcat_lines([outfile, potfile])


def _verify_cmd_template(fmt, archive, tools):
    tool, _method = _pick_verify_tool(fmt, tools)
    return [tool, "t", "-p<PASSWORD>", str(archive)]


def _verify_zip_stdlib(archive, password):
    try:
        with zipfile.ZipFile(str(archive)) as zf:
            infos = zf.infolist()
            if not infos:
                return False
            zf.read(infos[0], pwd=password.encode("utf-8", errors="replace"))
        return True
    except Exception:
        return False


def verify_password(archive, fmt, password, tools):
    """用 7z/unrar/rar 复核；返回 (是否通过, 复核方式)。复核失败视为假阳性。"""
    if fmt == "zip":
        _check_zip_encrypted(archive)
    if fmt in ("zip", "7z"):
        tool = tools.get("sevenz")
        if tool:
            proc = run_cmd([tool, "t", "-p" + password, str(archive)])
            if proc.returncode == 0:
                return True, "7z"
        if fmt == "zip":
            return _verify_zip_stdlib(archive, password), "zipfile"
        if tool:
            raise AcrackError("复核失败：%s 无法用该密码打开 %s（rc=%s），多为 7z 可执行文件不可用或档案损坏" % (tool, archive, proc.returncode))
        raise AcrackError("缺少复核工具：7z 需要 7z（可用 --engines 指定）")
    tool = tools.get("unrar")
    method = "unrar"
    if not tool:
        tool = tools.get("rar")
        method = "rar"
    if not tool:
        tool = tools.get("sevenz")
        method = "7z"
    if not tool:
        raise AcrackError("缺少复核工具：rar 需要 unrar / rar / 7z（可用 --engines 指定）")
    proc = run_cmd([tool, "t", "-p" + password, str(archive)])
    return proc.returncode == 0, method


def _dry_run(args, fmt, tools, engine, backend, extract_cmd, hashes, warning=None):
    archive = str(args.archive.resolve())
    tmp = Path(tempfile.gettempdir())
    mode = None
    mode_candidates = []
    if engine == "hashcat":
        allowed = LEGACY_PKZIP_MODES if args.engine == "hashcat" and hashes and hashes[0].startswith("$pkzip$") else None
        mode, mode_candidates = resolve_hashcat_mode(tools["hashcat"], hashes, fmt, allowed=allowed)
        hashfile = str(tmp / ("crumbs_%d_hashes.txt" % os.getpid()))
        potfile = str(tmp / ("crumbs_%d.pot" % os.getpid()))
        outfile = str(tmp / ("crumbs_%d_out.txt" % os.getpid()))
        crack_cmd = _hashcat_cmd(tools["hashcat"], mode, args, backend, hashfile, potfile, outfile)
    else:
        potfile = str(tmp / ("crumbs_%d.pot" % os.getpid()))
        hashfile = str(tmp / ("crumbs_%d_hashes.txt" % os.getpid()))
        crack_cmd = _john_cmd(tools["john"], args, hashfile, potfile)
    stdin_src = None
    if args.attack == "hybrid" and engine == "john":
        stdin_src = str(args.wordlist.resolve())
    verify_cmd = _verify_cmd_template(fmt, archive, tools)
    if args.json:
        print(json.dumps({
            "dry_run": True,
            "format": fmt,
            "engine": engine,
            "backend": backend,
            "warning": warning,
            "mode": args.attack,
            "hashcat_mode": mode,
            "mode_candidates": mode_candidates,
            "commands": {"extract": extract_cmd, "crack": crack_cmd, "verify": verify_cmd, "stdin": stdin_src},
        }, ensure_ascii=False))
    else:
        print("[提取] %s" % extract_cmd)
        print("[破解] %s" % crack_cmd)
        if stdin_src:
            print("[输入] %s" % stdin_src)
        print("[复核] %s" % verify_cmd)
        if warning:
            print("[警告] %s" % warning)
    return EXIT_FOUND


def _report_found(args, engine, backend, password, duration, verification, mode_candidates=None, warning=None,
                 hashcat_mode=None, length_hint=None):
    if args.json:
        print(json.dumps({
            "found": True,
            "password": password,
            "engine": engine,
            "backend": backend,
            "warning": warning,
            "hashcat_mode": hashcat_mode,
            "mode": args.attack,
            "duration_s": round(duration, 3),
            "attempts_hint": None,
            "verification": verification,
            "mask_length": length_hint,
            "mode_candidates": mode_candidates or [],
        }, ensure_ascii=False))
    else:
        ui_headline("ok", "已找到密码: %s" % password)
        rows = []
        if length_hint is not None:
            rows.append(("本轮掩码长度", "%d 位" % length_hint))
        rows += [
            ("引擎", engine + (" (%s)" % backend if backend else "")),
            ("hashcat 模式", hashcat_mode or "无"),
            ("攻击模式", args.attack),
            ("耗时", "%.3f 秒" % duration),
            ("复核方式", verification or "无"),
        ]
        if warning:
            rows.append(("警告", warning))
        ui_table(rows)
    return EXIT_FOUND


def _report_not_found(args, engine, backend, duration, mode_candidates=None, warning=None,
                      hashcat_mode=None, length_range=None):
    if args.json:
        print(json.dumps({
            "found": False,
            "password": None,
            "engine": engine,
            "backend": backend,
            "warning": warning,
            "hashcat_mode": hashcat_mode,
            "mode": args.attack,
            "duration_s": round(duration, 3),
            "attempts_hint": None,
            "verification": None,
            "length_range": list(length_range) if length_range else None,
            "mode_candidates": mode_candidates or [],
        }, ensure_ascii=False))
    else:
        ui_headline("bad", "未找到密码")
        rows = []
        if length_range:
            rows.append(("尝试长度", "%d-%d 位（逐位尝试）" % (length_range[0], length_range[1])))
        rows += [
            ("引擎", engine + (" (%s)" % backend if backend else "")),
            ("hashcat 模式", hashcat_mode or "无"),
            ("攻击模式", args.attack),
            ("耗时", "%.3f 秒" % duration),
            ("复核方式", "无"),
        ]
        if warning:
            rows.append(("警告", warning))
        ui_table(rows)
    return EXIT_NOT_FOUND


def _mask_lengths(args):
    """--len-min/--len-max 给出时返回逐位尝试的长度列表，否则 None。"""
    lo = getattr(args, "len_min", None)
    hi = getattr(args, "len_max", None)
    if lo is None or hi is None:
        return None
    return list(range(lo, hi + 1))


def _emit_report(args, res, length_hint=None, length_range=None):
    if res.get("password") is not None:
        return _report_found(args, res["engine"], res["backend"], res["password"], res["duration"],
                             res["verification"], res.get("mode_candidates"),
                             warning=res.get("warning"), hashcat_mode=res.get("hashcat_mode"),
                             length_hint=length_hint)
    return _report_not_found(args, res["engine"], res["backend"], res["duration"],
                             res.get("mode_candidates"), warning=res.get("warning"),
                             hashcat_mode=res.get("hashcat_mode"), length_range=length_range)


def _crack_body(args):
    """跑一轮破解并返回结果字典；最终报告由 run_crack 打印。"""
    fmt = detect_format(args.archive)
    if fmt is None:
        raise AcrackError(
            "无法识别的压缩格式: %s（扩展名 %s 仅作辅助，不参与判定）" % (args.archive, args.archive.suffix or "无")
        )
    _validate_attack_args(args)
    cfg, cfg_dir = read_engines(args.engines)
    tools = resolve_tools(cfg, cfg_dir)
    engine, backend, engine_warning = select_engine(tools, cfg, args.engine, probe_backend=True)
    if engine is None:
        raise AcrackError("未找到可用引擎（hashcat 或 john）：请安装，或用 --engines 指定 engines.json")
    if not args.dry_run and args.wordlist is not None and not args.wordlist.is_file():
        raise AcrackError("字典文件不存在: %s" % args.wordlist)
    if fmt == "zip" and not args.dry_run:
        _check_zip_encrypted(args.archive)

    result = {"fmt": fmt, "engine": engine, "backend": backend, "warning": engine_warning,
              "password": None, "verification": None, "duration": 0.0,
              "mode_candidates": [], "hashcat_mode": None, "dry_run": bool(args.dry_run)}

    if args.dry_run:
        extractor, _ = extractor_for_format(tools, fmt)
        extract_cmd = build_extract_cmd(extractor, args.archive, tools.get("perl"))
        hashes = extract_hashes(extract_cmd)
        result.update({"engine": engine, "backend": backend, "warning": engine_warning})
        _dry_run(args, fmt, tools, engine, backend, extract_cmd, hashes, warning=engine_warning)
        return result

    tmp = Path(tempfile.mkdtemp(prefix="crumbs_"))
    try:
        extractor, _ = extractor_for_format(tools, fmt)
        extract_cmd = build_extract_cmd(extractor, args.archive, tools.get("perl"))
        hashes = extract_hashes(extract_cmd)
        hashfile = tmp / "hashes.txt"
        with hashfile.open("w", encoding="utf-8", errors="replace") as fh:
            fh.write("\n".join(hashes) + "\n")
        mode_candidates = []
        hashcat_mode = None
        started = time.time()
        if engine == "hashcat":
            allowed = LEGACY_PKZIP_MODES if hashes and hashes[0].startswith("$pkzip$") else None
            mode, mode_candidates = resolve_hashcat_mode(tools["hashcat"], hashes, fmt, allowed=allowed)
            hashcat_mode = mode
            hc_tmp = Path(tempfile.mkdtemp(prefix="crumbs_hc_"))
            try:
                potfile = hc_tmp / "hashcat.pot"
                outfile = hc_tmp / "hashcat.out"
                crack_cmd = _hashcat_cmd(tools["hashcat"], mode, args, backend, hashfile, potfile, outfile)
                print("正在用 hashcat (%s) 破解，模式 %s；运行期间不打印进度，结束会显示结果"
                      % (backend, mode), file=sys.stderr)
                proc = run_cmd(crack_cmd, cwd=_hashcat_cwd(tools["hashcat"]))
                marker = _match_fatal_marker(proc, HASHCAT_MEM_MARKERS + FATAL_MARKERS)
                if marker and proc.returncode != 0 and args.engine == "auto" and tools.get("john"):
                    kind = "GPU/OpenCL 致命错误" if marker in HASHCAT_MEM_MARKERS else "无法处理该哈希"
                    print("警告: hashcat 报%s '%s'，自动改用 john 重跑" % (kind, marker), file=sys.stderr)
                    engine = "john"
                    backend = "cpu"
                    engine_warning = "hashcat 报%s（%s），已自动回退 john" % (kind, marker)
                    jpotfile = tmp / "john.pot"
                    crack_cmd = _john_cmd(tools["john"], args, hashfile, jpotfile)
                    proc = run_cmd(crack_cmd, cwd=str(tmp), stdin_path=_john_stdin_path(args))
                    check_crack_result(proc, "john")
                    show = run_cmd([tools["john"], "--show", "--pot=%s" % jpotfile, str(hashfile)], cwd=str(tmp))
                    check_crack_result(show, "john")
                    candidates = parse_john_show(show.stdout or "")
                else:
                    check_crack_result(proc, "hashcat")
                    candidates = _extract_hashcat_password(outfile, potfile)
            finally:
                shutil.rmtree(hc_tmp, ignore_errors=True)
        else:
            potfile = tmp / "john.pot"
            crack_cmd = _john_cmd(tools["john"], args, hashfile, potfile)
            proc = run_cmd(crack_cmd, cwd=str(tmp), stdin_path=_john_stdin_path(args))
            check_crack_result(proc, "john")
            show = run_cmd([tools["john"], "--show", "--pot=%s" % potfile, str(hashfile)], cwd=str(tmp))
            check_crack_result(show, "john")
            candidates = parse_john_show(show.stdout or "")
        duration = time.time() - started
        result.update({"engine": engine, "backend": backend, "warning": engine_warning,
                       "duration": duration, "mode_candidates": mode_candidates,
                       "hashcat_mode": hashcat_mode})
        for cand in candidates:
            if not cand:
                continue
            ok, verification = verify_password(args.archive, fmt, cand, tools)
            if ok:
                result.update({"password": cand, "verification": verification})
                break
            print("[!] 复核未通过，忽略假阳性候选: %s" % cand, file=sys.stderr)
        return result
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_crack(args):
    # 先校验一次：逐位尝试的结尾长度可能被组合数上限截短，长度列表要在截短之后再生
    _validate_attack_args(args)
    lengths = _mask_lengths(args)
    if lengths is None:
        res = _crack_body(args)
        if res.pop("dry_run"):
            return EXIT_FOUND
        return _emit_report(args, res)

    if args.dry_run:
        for length in lengths:
            if _keyspace_one(args, length) > _HC_KEYSPACE_LIMIT:
                ui_warn("%d 位起超出 hashcat 单次上限，后面的位数不再尝试" % length)
                break
            sub = argparse.Namespace(**vars(args))
            sub.mask = args.mask * length
            sub.len_min = sub.len_max = None  # 掩码已展开成完整长度，别再让校验重复相乘
            ui_progress(length, lengths[-1], "长度 %d 位" % length, sub.mask)
            _crack_body(sub)
        return EXIT_FOUND

    unit = args.mask or ""
    total_started = time.time()
    last = None
    done = []
    for i, length in enumerate(lengths, 1):
        # 每轮单独比上限：这一位撑得住才跑，撑不住就停（更长的位数只会更大）
        if _keyspace_one(args, length) > _HC_KEYSPACE_LIMIT:
            ui_warn("%d 位的组合数超出 hashcat 单次上限 2^64，停止逐位尝试" % length)
            break
        sub = argparse.Namespace(**vars(args))
        sub.mask = unit * length
        sub.len_min = sub.len_max = None  # 掩码已展开成完整长度，别再让校验重复相乘
        label = "字典词 + %d 位后缀" % length if args.attack == "hybrid" else "%d 位" % length
        ui_progress(i, len(lengths), label, sub.mask)
        res = _crack_body(sub)
        res["duration"] = time.time() - total_started
        if res.get("password") is not None:
            ui_ok("第 %d 轮命中，长度 %d 位" % (i, length))
            return _emit_report(sub, res, length_hint=length)
        ui_info("第 %d 轮未命中（%s），继续下一位" % (i, label))
        last = res
        done.append(length)
    if not done:
        raise AcrackError("没有可尝试的位数：起始长度的组合数已超出 hashcat 单次上限 2^64≈1.8e19，"
                          "请缩小字符集或改用字典")
    span = (done[0], done[-1])
    ui_warn("已尝试 %d-%d 位全部长度，均未命中" % span)
    last = last or {"engine": None, "backend": None, "warning": None, "duration": 0.0}
    last["duration"] = time.time() - total_started
    return _emit_report(args, last, length_range=span)


# ---------------- 交互式向导 ----------------
WIZ_CHARSETS = [
    ("1", "?d", None, "纯数字 0-9"),
    ("2", "?l", None, "小写字母 a-z"),
    ("3", "?u", None, "大写字母 A-Z"),
    ("4", "?1", "?d?l", "数字 + 小写字母"),
    ("5", "?1", "?d?l?u", "数字 + 大小写字母"),
    ("6", "?a", None, "全部可打印字符（含符号，最慢）"),
]
_CHARSET_SIZES = {"d": 10, "l": 26, "u": 26, "s": 33, "a": 95, "b": 256}


def _charset_size(cs):
    total = 0
    literals = set()
    i = 0
    while i < len(cs):
        if cs[i] == "?" and i + 1 < len(cs) and cs[i + 1] in _CHARSET_SIZES:
            total += _CHARSET_SIZES[cs[i + 1]]
            i += 2
            continue
        literals.add(cs[i])
        i += 1
    return total + len(literals)


def _mask_total(mask, cs1=None):
    total = 1
    i = 0
    while i < len(mask):
        c = mask[i]
        if c == "?" and i + 1 < len(mask):
            nxt = mask[i + 1]
            if nxt in _CHARSET_SIZES:
                total *= _CHARSET_SIZES[nxt]
            elif nxt == "1" and cs1:
                total *= _charset_size(cs1)
            i += 2
            continue
        i += 1
    return total


_HC_KEYSPACE_LIMIT = 2 ** 64 - 1


def _wordlist_lines(path):
    """字典里非空行数，用于估算组合数（数不出来就当 1）。"""
    n = 0
    try:
        with open(path, "rb") as f:
            for line in f:
                if line.strip():
                    n += 1
    except OSError:
        return 1
    return max(1, n)


def _keyspace_for(args, mask):
    """一段掩码的组合数（hybrid 已乘字典行数）。"""
    n = _mask_total(mask, getattr(args, "charset1", None))
    if args.attack == "hybrid":
        n *= _wordlist_lines(args.wordlist)
    return n


def _keyspace_one(args, length):
    """逐位尝试时某一轮（固定长度）的组合数。"""
    return _keyspace_for(args, (args.mask or "") * length)


def _keyspace_worst(args):
    """本次攻击单轮的最大组合数（不是所有长度合计）。"""
    lens = _mask_lengths(args)
    if lens is None:
        return _keyspace_for(args, args.mask or "")
    return max(_keyspace_one(args, n) for n in lens)


def _fmt_count(n):
    if n >= 100000000:
        return "%.1f 亿" % (n / 1e8)
    if n >= 10000:
        return "%.1f 万" % (n / 1e4)
    return str(n)


def _wiz_ask(prompt, default=None):
    while True:
        try:
            raw = input(prompt)
        except EOFError:
            raise AcrackError("交互输入结束，已取消。脚本里请直接用: crumbs crack -a ... ")
        s = _strip_invisibles(raw).strip().strip('"').strip("'")
        if not s and default is not None:
            return default
        if s:
            return s


def _wiz_choice(prompt, options, default):
    while True:
        s = _wiz_ask(prompt, default).lower()
        if s in options:
            return s
        print("  输入无效，可选: %s" % " / ".join(sorted(options)))


def run_wizard(archive=None):
    ui_banner("crumbs-cracker  压缩包密码破解", "交互模式：直接回车用括号里的默认值，Ctrl+C 退出")
    if not archive:
        archive = _wiz_ask("压缩包路径（可以把文件拖进来）: ")
    p = Path(archive)
    if not p.exists():
        raise AcrackError("文件不存在: %s" % p)
    cfg, cfg_dir = read_engines(None)
    tools = resolve_tools(cfg, cfg_dir)
    fmt = detect_format(p)
    ui_table([("文件", p), ("格式", fmt or "未识别（仍会尝试提取）")])

    print("")
    print("破解方式：")
    print("  1) 字典     用词表逐条试（最快，建议先跑这个）")
    print("  2) 纯暴力   按字符集穷举固定长度（不知道内容时用）")
    print("  3) 混合     字典里的词 + 固定后缀，如 secret + 2 位数字")
    mode = _wiz_choice("请选择 [1-3]（默认 2）: ", {"1", "2", "3"}, "2")
    attack = {"1": "wordlist", "2": "mask", "3": "hybrid"}[mode]

    wordlist = None
    if attack != "mask":
        default_wl = ""
        for cand in (Path("dicts/common.txt"), PROJECT_ROOT / "dicts" / "common.txt",
                     Path("samples/words.txt"), PROJECT_ROOT / "samples" / "words.txt"):
            if cand.is_file():
                default_wl = str(cand)
                break
        for _ in range(3):
            tip = "（回车用 %s）" % default_wl if default_wl else ""
            wl = _wiz_ask("字典文件路径%s: " % tip, default_wl or None)
            if wl and Path(wl).is_file():
                wordlist = Path(wl)
                break
            print("  文件不存在: %s" % wl)
        if wordlist is None:
            raise AcrackError("没有可用的字典文件")

    length = 0
    len_min = None
    len_max = None
    if attack == "mask":
        length_tip = "密码长度【1-16，不知道长度就输 0】: "
    elif attack == "hybrid":
        length_tip = "后缀长度（字典词后面还有几位）【1-16，不知道就输 0】: "
    else:
        length_tip = None
    if length_tip:
        while True:
            raw = _wiz_ask(length_tip, "4" if attack == "mask" else "2")
            if raw.isdigit() and 0 <= int(raw) <= 16:
                length = int(raw)
                break
            print("  请输入 0-16 的整数（0 表示不知道长度）")
        if length == 0:
            while True:
                raw = _wiz_ask("从几位开始尝试【1-16】（默认 1）: ", "1")
                if raw.isdigit() and 1 <= int(raw) <= 16:
                    len_min = int(raw)
                    break
                print("  请输入 1-16 的整数")
            while True:
                raw = _wiz_ask("到几位结束（含）【%d-16】（默认 6）: " % len_min, "6")
                if raw.isdigit() and len_min <= int(raw) <= 16:
                    len_max = int(raw)
                    break
                print("  请输入 %d-16 的整数" % len_min)
            length = len_min
            print("  将按 %d → %d 位逐位尝试，前一位没出来才试下一位" % (len_min, len_max))

    token = None
    cs1 = None
    if attack == "wordlist":
        pick = None
    else:
        print("")
        print("密码包含的字符：")
        for key, _tok, _cs, desc in WIZ_CHARSETS:
            print("  %s) %s" % (key, desc))
        print("  7) 自定义字符集（逐项询问：数字 / 小写 / 大写 / 符号 / 其它）")
        pick = _wiz_choice("请选择 [1-7]（默认 1）: ", {"1", "2", "3", "4", "5", "6", "7"}, "1")
        if pick == "7":
            print("")
            print("自定义字符集（逐项回答 y/n）：")
            parts = []
            if _wiz_choice("  包含数字 0-9？【Y/n】: ", {"y", "n"}, "y") == "y":
                parts.append("?d")
            if _wiz_choice("  包含小写字母 a-z？【Y/n】: ", {"y", "n"}, "y") == "y":
                parts.append("?l")
            if _wiz_choice("  包含大写字母 A-Z？【y/N】: ", {"y", "n"}, "n") == "y":
                parts.append("?u")
            if _wiz_choice("  包含特殊符号（!@#%^&* 等）？【y/N】: ", {"y", "n"}, "n") == "y":
                parts.append("?s")
            extra = _wiz_ask("  还要加入其它字符？（直接输入，回车跳过）: ", "")
            if extra:
                parts.append(extra.replace("?", "??"))
            if not parts:
                print("  一项都没选，改用全部可打印字符")
                parts.append("?a")
            cs1 = "".join(parts)
            token = "?1"
        else:
            hit = [x for x in WIZ_CHARSETS if x[0] == pick][0]
            token, cs1 = hit[1], hit[2]
    ranged = len_min is not None and len_max is not None
    mask = (token if ranged else token * length) if (token and length) else ""
    if attack in ("mask", "hybrid") and mask:
        _wl_n = _wordlist_lines(Path(wordlist)) if (attack == "hybrid" and wordlist) else 1
        _what = "后缀长度" if attack == "hybrid" else "密码长度"
        if ranged:
            _bad = [n for n in range(len_min, len_max + 1)
                    if _mask_total(mask * n, cs1) * _wl_n > _HC_KEYSPACE_LIMIT]
            if _bad and _bad[0] == len_min:
                raise AcrackError("组合数过大：%d 位单轮约 %.3g 种，超出单次可枚举上限 1.8e19；"
                                  "请缩小字符集或改用字典"
                                  % (len_min, _mask_total(mask * len_min, cs1) * _wl_n))
            if _bad:
                print("  提示: %d 位起超出单次上限，本次只尝试 %d-%d 位（更长的%s请缩小字符集）"
                      % (_bad[0], len_min, _bad[0] - 1, _what))
                len_max = _bad[0] - 1
        else:
            _total = _mask_total(mask, cs1) * _wl_n
            if _total > _HC_KEYSPACE_LIMIT:
                raise AcrackError("组合数约 %.3g，超出单次可枚举上限 1.8e19；请缩短%s或缩小字符集"
                                  % (_total, _what))

    print("")
    gpu = _wiz_choice("是否尝试 GPU 加速？（需要 NVIDIA/AMD 驱动 + hashcat 可用）【y/N】: ",
                      {"y", "n"}, "n")
    backend = "cpu"
    if gpu == "y":
        hc = tools.get("hashcat")
        probe = probe_gpu(hc) if hc else {"available": False, "devices": []}
        if probe["available"]:
            print("  已检测到 GPU: %s" % ", ".join(probe["devices"]))
            print("  引擎: 自动（优先 hashcat/GPU，失败会自动改 john）")
            engine = None
            backend = "gpu"
        else:
            print("  未检测到可用 GPU，本次仍用 CPU（john）")
            engine = "john" if tools.get("john") else None
            backend = "cpu"
    else:
        engine = "john" if tools.get("john") else None

    print("")
    print("-" * 56)
    print("破解方式: %s" % {"wordlist": "字典", "mask": "纯暴力", "hybrid": "混合"}[attack])
    if wordlist is not None:
        print("字典: %s" % wordlist)
    if mask:
        if ranged:
            print("掩码单元: %s（逐位尝试 %d-%d 位）" % (mask, len_min, len_max))
        else:
            print("掩码: %s" % mask)
    if cs1:
        print("字符集 ?1 = %s（%d 种）" % (cs1, _charset_size(cs1)))
    if attack == "mask" or ranged:
        if ranged:
            total = sum(_mask_total(mask * n, cs1) for n in range(len_min, len_max + 1))
            print("组合数: %s（%d-%d 位合计）" % (_fmt_count(total), len_min, len_max))
        else:
            print("组合数: %s" % _fmt_count(_mask_total(mask, cs1)))
    print("引擎: %s" % ("自动（优先 hashcat/GPU，失败自动改 john）" if engine is None else engine) + (" (%s)" % backend if engine else ""))
    print("-" * 56)
    if _wiz_choice("开始破解？【Y/n】: ", {"y", "n"}, "y") != "y":
        print("已取消")
        return EXIT_ERROR

    argv = ["crack", "-a", attack, str(p)]
    if wordlist is not None:
        argv += ["-w", str(wordlist)]
    if mask:
        argv += ["-m", mask]
    if ranged:
        argv += ["--len-min", str(len_min), "--len-max", str(len_max)]
    if cs1:
        argv += ["-1", cs1]
    if engine:
        argv += ["--engine", engine]
    print("")
    return main(argv)


def _stdin_is_tty():
    try:
        return bool(sys.stdin and sys.stdin.isatty())
    except Exception:
        return False


def _wizard_requested(argv):
    if os.environ.get("CRUMBS_NO_WIZARD"):
        return False
    if not (os.environ.get("CRUMBS_FORCE_WIZARD") == "1" or _stdin_is_tty()):
        return False
    if not argv:
        return True
    if len(argv) != 1:
        return False
    arg = argv[0]
    if arg.startswith("-") or arg in ("check", "crack"):
        return False
    return Path(arg).exists()


def main(argv=None):
    configure_stdio()
    argv = [_strip_invisibles(a) for a in (sys.argv[1:] if argv is None else argv)]
    if _wizard_requested(argv):
        try:
            return run_wizard(argv[0] if argv else None)
        except AcrackError as exc:
            print("错误: %s" % exc, file=sys.stderr)
            return EXIT_ERROR
        except KeyboardInterrupt:
            print("已中断", file=sys.stderr)
            return EXIT_ERROR
    if (len(argv) == 1 and not argv[0].startswith("-")
            and argv[0] not in ("check", "crack") and not Path(argv[0]).exists()):
        print("错误: 文件不存在: %s" % argv[0], file=sys.stderr)
        print("      用法: crumbs 压缩包.zip  进入交互式，或 crumbs crack -a ... 直接指定参数", file=sys.stderr)
        return EXIT_ERROR
    if (len(argv) == 1 and not argv[0].startswith("-")
            and argv[0] not in ("check", "crack") and Path(argv[0]).exists()):
        print("提示: 只给一个压缩包是交互式用法，但当前输入不是终端，无法问答。", file=sys.stderr)
        print("      非交互写法: crumbs crack -a mask -m '?d?d?d?d' 文件", file=sys.stderr)
        print("                  crumbs crack -a wordlist -w 字典.txt 文件", file=sys.stderr)
        return EXIT_ERROR
    args = build_parser().parse_args(argv)
    try:
        if args.command == "check":
            return run_check(args)
        return run_crack(args)
    except AcrackError as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        print("已中断", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
