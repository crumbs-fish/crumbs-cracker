crumbs-cracker 便携版（Linux x86-64）
=====================================

零安装：解压即用，不写系统目录、不需要 root、不改 PATH。

包含内容
--------
  crumbs_cracker.py / crumbs-cracker.sh      驱动（Python 3 标准库，单文件）
  engines/john/run/john      john-jumbo 1.9.0（CPU 多线程，OpenMP）
  engines/john/run/zip2john  提取器（bash 包装脚本，内部 exec -a 调用同一个 john 二进制）
  engines/john/run/rar2john
  engines/john/run/7z2john.pl
  engines/bin/7z2john        Perl 包装器（自带 Compress::Raw::Lzma，无需 root 装模块）
  engines/bin/7zz            静态 7-Zip 命令行（用于 7z / zip / rar 复核）
  engines/bin/unrar          unrar（用于 rar 复核）
  engines/hashcat/hashcat.bin  hashcat 6.2.6（GPU 加速引擎，只带压缩包族模块）
  engines/hashcat/OpenCL/      hashcat 内核源码（首次运行按本机显卡现编）
  engines/engines.json       相对路径配置，换机器不用改
  samples/                   九个加密样本（密码 secret / 1234 / secret42）+ 两个词表

环境要求
--------
  Linux x86-64，glibc（在 Debian 12 上构建与验证）
  python3 >= 3.8（签名压缩包驱动本身）
  perl（仅 7z 提取需要；zip/rar 不需要）

交互式（只给一个压缩包就会问答：破解方式、字典、长度、字符、是否 GPU）
--------
  ./crumbs-cracker.sh samples/zipaes.zip

快速开始
--------
  7z x crumbs-cracker-portable-linux-x64-*.7z      # 7z / 7zz / p7zip 均可，解压保留可执行权限
  cd crumbs-cracker-portable
  ./crumbs-cracker.sh check samples/zipaes.zip --json
  ./crumbs-cracker.sh crack -a wordlist -w samples/words.txt samples/zipaes.zip

自检（应输出 found=true / password=secret）
--------
  for f in samples/zipaes.zip samples/sevenz.7z samples/rar5.rar; do
    ./crumbs-cracker.sh crack -a wordlist -w samples/words.txt "$f" --json
  done
  # 反例：必须 found=false，验证不是假阳性
  ./crumbs-cracker.sh crack -a wordlist -w samples/words_bad.txt samples/rar5.rar; echo "exit=$?"

退出码：0 找到 / 1 未找到 / 2 环境或参数错误。

引擎说明
--------
  默认 auto：先运行时探测（hashcat -I）。探测到 GPU -> hashcat(GPU)，
  否则 -> john（纯 CPU，OpenMP 多线程）。hashcat 运行中报内存/OpenCL 致命错误时，
  auto 会自动改用 john 重跑一次（--engine hashcat 强制时不会回退）。
  GPU 需要显卡厂商驱动（NVIDIA 走 CUDA/OpenCL，AMD 走 ROCm/OpenCL）；
  没有驱动时 hashcat -I 识别不到 GPU，auto 自然走 john。
  模式不做静态猜测，一律由 hashcat --identify 判定；已实测：
  13600 zip AES、17200/17210/17220/17225/17230 zip ZipCrypto、
  11600 7z、12500/23700/23800 rar4（RAR3-hp / RAR3-p）、13000 rar5。
  rar4 走 23800（RAR3-p），RTX 4060 实测约 3.1 万 H/s，比 CPU（john 135 H/s）快两个数量级，
  auto 有 GPU 时一律优先 hashcat。

支持格式
--------
  zip（ZipCrypto / AES-256 / 多条目）、7z（含加密文件名）、rar4、rar5
  攻击模式：wordlist、mask、hybrid（词表 + 掩码）

Windows
--------
  本包是 Linux 版。Windows 便携包见同目录 crumbs-cracker-portable-win64-*.7z。

内置字典：dicts/common.txt（1 万条）、dicts/common-100k.txt（10 万条），交互式默认用它。
