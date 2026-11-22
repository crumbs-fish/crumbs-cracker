crumbs-cracker 便携版（Windows x64）
=====================================

零安装：解压即用，不写注册表、不改 PATH、不需要管理员权限。

交互式：只给一个压缩包就会问答
--------
  crumbs-cracker.bat samples\rar5.rar
  依次问 破解方式 -> 字典位置(纯暴力跳过) -> 密码长度 -> 包含字符 -> 是否尝试 GPU

解压（单文件自解压 .exe，最大压缩比）
--------
  本包是 7-Zip 自解压单文件 .exe（LZMA2 最大压缩，约 34 MB，解开约 191 MB）：
      双击即可，或命令行：
      crumbs-portable-win64-sfx.exe -y                解压到当前目录
      crumbs-portable-win64-sfx.exe -o"D:\tools" -y  解压到指定目录
  解压后进入 crumbs-cracker-portable-win64 目录再运行 crumbs-cracker.bat——engines\ 与 python\ 必须和它同级。
  解压出来的文件不会自我删除，想换地方直接把整个目录搬走即可。
  注意：老一些的杀软可能对自解压 exe 报「未知的自解压程序」，加一次信任即可；
  也可以改用 .7z 分发版（需 7-Zip / WinRAR 解压）。

包含内容
--------
  crumbs_cracker.py                  驱动（Python 3 标准库，单文件）
  crumbs-cracker.bat                 启动器（自动使用包内 python，可接受拖放参数）
  python\python.exe          Python 3.12.10 嵌入式运行时（无需另装 Python）
  engines\john\run\john.exe  john-jumbo 1.9.0（CPU 多线程）
  engines\john\run\zip2john.exe    zip 哈希提取器
  engines\john\run\rar2john.exe    rar 哈希提取器
  engines\bin\7z.exe + 7z.dll      7-Zip（7z/zip/rar 复核）
  engines\bin\7z2hashcat.exe        7z 哈希提取器（原生 exe，无需 Perl）
  engines\hashcat\hashcat.exe       hashcat 6.2.6（GPU 加速引擎，只带压缩包族模块）
  engines\hashcat\OpenCL\           hashcat 内核源码（首次运行按本机显卡现编）
  engines\engines.json       相对路径配置，换机器不用改
  samples\                   九个加密样本（密码 secret / 1234 / secret42）+ 两个词表

环境要求
--------
  Windows 7 SP1 / 10 / 11 x64
  无需 Python、无需 Perl、无需 7-Zip、无需 WinRAR

快速开始（cmd 窗口）
--------
  cd /d 解压目录\crumbs-cracker-portable-win64
  crumbs-cracker.bat check samples\zipaes.zip
  crumbs-cracker.bat crack -a wordlist -w samples\words.txt samples\zipaes.zip
  crumbs-cracker.bat crack -a mask -m ?d?d?d?d samples\mask.zip
  crumbs-cracker.bat crack -a hybrid -w samples\words.txt -m ?d?d samples\hybrid.zip

自检（应输出 已找到密码: secret）
--------
  for %F in (zipaes.zip sevenz.7z rar5.rar) do crumbs-cracker.bat crack -a wordlist -w samples\words.txt samples\%F
  :: 反例：必须 未找到密码，验证不是假阳性
  crumbs-cracker.bat crack -a wordlist -w samples\words_bad.txt samples\rar5.rar & echo exit=%ERRORLEVEL%

退出码：0 找到 / 1 未找到 / 2 环境或参数错误。

引擎说明
--------
  默认 auto：先运行时探测（hashcat -I）。探测到 GPU -> hashcat(GPU)，
  否则 -> john（纯 CPU 多线程）。hashcat 运行中报内存/OpenCL 致命错误时，
  auto 会自动改用 john 重跑一次（--engine hashcat 强制时不会回退）。
  GPU 需要 NVIDIA/AMD 显卡驱动；没有驱动时 hashcat -I 识别不到 GPU，auto 走 john。
  模式不做静态猜测，一律由 hashcat --identify 判定；已实测：
  13600 zip AES、17200/17210/17220/17225/17230 zip ZipCrypto、
  11600 7z、12500/23700/23800 rar4（RAR3-hp / RAR3-p）、13000 rar5。
  rar4 走 23800（RAR3-p），RTX 4060 实测约 3.1 万 H/s，比 CPU（john 135 H/s）快两个数量级，
  auto 有 GPU 时一律优先 hashcat。

支持格式
--------
  zip（ZipCrypto / AES-256 / 多条目）、7z（含加密文件名）、rar4、rar5
  攻击模式：wordlist、mask、hybrid（词表 + 掩码）

中文显示
--------
  Windows 控制台默认代码页为 GBK 时中文正常显示；若出现乱码可先执行 chcp 65001。

内置字典：dicts\common.txt（1 万条）、dicts\common-100k.txt（10 万条），交互式默认用它。
