#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""组合数上限（2^64）守卫的回归测试。

规则：逐位尝试是一轮一次调用，所以按"单个长度"分别比上限——
撑得住就继续下一位，撑不住的那一位起（更长的只会更大）直接不试；
不能拿所有长度的合计或最大值去一刀切整个任务。
"""
import subprocess, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
AC = ROOT / 'crumbs-cracker.sh'
FX = pathlib.Path('/tmp/crumbs_fx')


def run(args, timeout=180):
    p = subprocess.run([str(AC)] + args, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout + p.stderr


def main():
    ok = True

    def check(name, cond, detail=''):
        nonlocal ok
        if cond:
            print('ok  ' + name)
        else:
            print('FAIL %s %s' % (name, detail[:300]))
            ok = False

    # 1) 单轮（不逐位）超限 -> 直接报错
    rc, out = run(['crack', '-a', 'hybrid', '-w', str(FX / 'words.txt'),
                   '-m', '?a' * 10, str(FX / 'hybrid.zip')])
    check('hybrid 单轮溢出 rc=2', rc == 2 and '组合数过大' in out, 'rc=%s' % rc)

    rc, out = run(['crack', '-a', 'mask', '-m', '?a' * 11, str(FX / 'mask.zip')])
    check('mask 单轮溢出 rc=2', rc == 2 and '组合数过大' in out, 'rc=%s' % rc)

    # 2) 逐位尝试：后面的位数超限只截断，前面的照常跑
    #    需要真样本 + 真引擎；CI 或新克隆的仓库没有 engines/，此时跳过实跑用例
    have_env = FX.exists() and (ROOT / 'engines' / 'engines.json').exists()
    if not have_env:
        print('skip 实跑用例：缺少 %s 或 engines/engines.json（先跑 tests/rebuild-fixtures.sh）' % FX)
        return 0 if ok else 1

    rc, out = run(['crack', '-a', 'mask', '-m', '?a', '--len-min', '1', '--len-max', '12',
                   '--dry-run', str(FX / 'mask.zip')])
    check('逐位 1-12 位截到 9 位（rc=0）', rc == 0 and '本次只逐位尝试 1-9 位' in out, 'rc=%s' % rc)
    check('逐位 1-12 位仍然尝试 1-9 位', '== 长度 9' in out and '== 长度 10' not in out)

    # 3) 起始长度本身超限 -> 整单报错（没有可试的位数）
    rc, out = run(['crack', '-a', 'mask', '-m', '?a', '--len-min', '10', '--len-max', '12',
                   str(FX / 'mask.zip')])
    check('起始 10 位即超限 rc=2', rc == 2 and '组合数过大' in out, 'rc=%s' % rc)

    # 4) 逐位尝试仍然能正常破（4 位数字）
    rc, out = run(['crack', '-a', 'mask', '-m', '?d', '--len-min', '1', '--len-max', '4',
                   str(FX / 'mask.zip')])
    check('逐位 ?d 1-4 位破出 1234', rc == 0 and '1234' in out and '第 4 轮命中' in out, 'rc=%s' % rc)

    # 5) 正常混合不受影响
    rc, out = run(['crack', '-a', 'hybrid', '-w', str(FX / 'words.txt'),
                   '-m', '?d?d', str(FX / 'hybrid.zip')])
    check('正常混合破出 secret42', rc == 0 and 'secret42' in out, 'rc=%s' % rc)

    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
