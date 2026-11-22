# crumbs 使用说明

crumbs_cracker.py 是一个跨平台（Linux / Windows）压缩包密码破解驱动脚本，只依赖 Python 标准库。
它负责：识别压缩格式、调用 john-jumbo 提取器提取哈希、按 GPU/CPU 情况选择 hashcat 或 john、
解析破解结果，并用 7z / unrar 复核明文，避免假阳性。

## 快速开始

    python3 crumbs_cracker.py check secret.zip
    python3 crumbs_cracker.py check secret.zip --json

    python3 crumbs_cracker.py crack secret.zip -a wordlist -w words.txt
    python3 crumbs_cracker.py crack secret.zip -a mask -m "?d?d?d?d"
    python3 crumbs_cracker.py crack secret.zip -a hybrid -w words.txt -m "?d?d"

    # 只打印将要执行的命令，不执行
    python3 crumbs_cracker.py crack secret.zip -a wordlist -w words.txt --dry-run

Windows 上使用启动器：

    crumbs-cracker.bat check secret.zip
    crumbs-cracker.bat crack secret.zip -a wordlist -w words.txt

## 内置字典（包内自带，开箱可用）

    dicts/common.txt        10050 条常用口令（首选，几秒钟跑完）
    dicts/common-100k.txt   100049 条（命中率更高，耗时约 10 倍）

常用口令取自 SecLists 的 10k-most-common 与 Pwdb top-100k，并在文件最前面固定加入以下
业务关键词的**大小写全变体**（每个词 2^n 种组合）与中文词：

    xyc  新英才  qzks  qmks  yk  ks

用法：

    ./crumbs-cracker.sh crack secret.zip -a wordlist -w dicts/common.txt
    crumbs-cracker.bat crack secret.zip -a wordlist -w dicts\common.txt

交互式问答里“字典位置”直接回车，默认就是 dicts/common.txt。

注意：内置字典只覆盖“常见弱口令 + 上述关键词原形”，像 qzks1234 这种“关键词+数字后缀”
要用混合攻击（-a hybrid -m '?d?d?d?d'）或规则文件（包里 engines/john/run/rules/ 有
best64、d3ad0ne、dive 等 13 个 .rule）。

## 交互式（只给压缩包）

    crumbs-cracker.bat  secret.zip
    ./crumbs-cracker.sh secret.zip
    python3 crumbs_cracker.py secret.zip

只给一个压缩包时进入问答，依次询问：

    1) 破解方式：字典 / 纯暴力 / 混合
    2) 字典位置（纯暴力跳过）
    3) 密码长度（字典方式跳过；混合方式是后缀长度）
       不知道长度就输 0：接着问「从几位开始」「到几位结束」，按 1->2->3… 逐位尝试，
       前一位整轮没出来才进入下一位，命中即停止，摘要里显示「掩码单元 + 逐位尝试 N-M 位」
    4) 密码包含的字符：纯数字 / 小写 / 大写 / 数字+小写 / 数字+大小写 / 全部可打印 / 自定义
       选“自定义”后会逐项追问：是否包含数字 / 小写 / 大写 / 特殊符号，最后可再补其它字符（回车跳过）
    5) 是否尝试 GPU：需要 NVIDIA/AMD 驱动 + hashcat；选 y 时检测到 GPU 才用 hashcat，否则仍用 john CPU

最后显示摘要（掩码、字符集大小、组合数、引擎与后端）并确认后开始。
非交互环境（管道、脚本）请直接用下面的 crack 子命令；也可用环境变量 CRUMBS_FORCE_WIZARD=1 强制问答、CRUMBS_NO_WIZARD=1 禁用问答。

## 子命令

check ARCHIVE
    只做三件事：识别格式、提取哈希、报告将使用哪个引擎（及 GPU/CPU 后端），不破解。

crack ARCHIVE -a MODE [选项]
    完整破解流程：识别 -> 提取 -> 破解 -> 7z/unrar 复核。

通用选项：
    --engine auto|hashcat|john   强制引擎（默认 auto：有 hashcat 用 hashcat，否则用 john）
    --engines PATH              指定 engines.json 路径，优先级最高
    --json                       输出结构化 JSON

crack 专属：
    -a, --attack wordlist|mask|hybrid
    -w, --wordlist FILE         字典文件（wordlist / hybrid 需要）
    -m, --mask MASK             掩码（mask / hybrid 需要）
    -1, --charset1 CHARSET      自定义字符集 1，掩码里用 ?1 引用，如 -1 '?d?l' -m '?1?1?1'
    --len-min N / --len-max N   不知道长度时逐位尝试：-m 只写单元，从 N 位试到 M 位
                                （mask / hybrid 都支持，两者必须同时给出，1<=N<=M<=16）
    --dry-run                   只打印命令列表，不执行

## 攻击模式映射

    wordlist    hashcat -a 0 HASHFILE WORDLIST
                john --wordlist=WORDLIST

    mask        hashcat -a 3 HASHFILE 'MASK'
                john --mask='MASK'

    hybrid      hashcat -a 6 HASHFILE WORDLIST 'MASK'
                john --stdin --mask='?wMASK'（字典从 stdin 读入，不落临时文件）

不知道长度（逐位尝试）：

    crumbs-cracker.sh crack -a mask   -m '?d' --len-min 1 --len-max 6 secret.zip
    crumbs-cracker.sh crack -a hybrid -m '?d' --len-min 1 --len-max 4 -w dicts/common.txt secret.rar

    实际执行：?d、?d?d、?d?d?d … 逐轮跑完，命中即停；每轮前打印「第 i/N 轮：N 位（掩码 …）」
    JSON 输出里 found 时带 "mask_length"，未找到时带 "length_range"

## GPU 加速（hashcat）

需要 NVIDIA/AMD 驱动 + hashcat 可用；auto 检测到 GPU 才走 hashcat(gpu)，否则 john(cpu)。
--engine hashcat 可强制：未检测到 GPU 时以 CPU 运行（可能极慢）。

支持模式：
    13600  zip AES
    17200 / 17210 / 17220 / 17225  zip ZipCrypto
    11600  7z
    12500 / 23700 / 23800  rar4（RAR3-hp / RAR3-p 压缩 / 未压缩）
    13000  rar5

实测速度（RTX 4060 + hashcat 6.2.6，仅破解阶段，hashcat -b 机器可读输出）：
    13600 ≈ 2930 kH/s；11600 ≈ 510 kH/s；13000 ≈ 48.2 kH/s；23800 ≈ 30.7 kH/s
    zip ZipCrypto（17225）≈ 96 亿 H/s
本机 2 核 CPU + john（含提取与复核）：zip 54 kH/s、7z 51.8 H/s、rar5 837 H/s、rar4 135 H/s。
提醒：7z 即使有 GPU 也慢（比 zip AES 慢约 5700 倍），掩码空间大时先想别的思路。
注意：真实破解只喂几条候选时 hashcat 报的 Speed 是启动开销，没有参考价值；
     判断吞吐一律用 hashcat -b。

## 格式识别

按文件头魔术字节识别，扩展名只作辅助提示：
    ZIP   PK\x03\x04 / PK\x05\x06 / PK\x07\x08
    7z    7z\xbc\xaf\x27\x1c
    RAR4  Rar!\x1a\x07\x00
    RAR5  Rar!\x1a\x07\x01\x00

无法识别时退出码 2。

## 引擎选择规则

1. 强制 --engine hashcat 或 --engine john 时直接使用对应引擎。
   --engine hashcat 未检测到 GPU 时仍用 hashcat，后端为 cpu，并提示"可能极慢"。
2. auto 模式：hashcat 可用时先运行 hashcat -I 运行时探测（优先级高于 engines.json）：
   出现任一 GPU 设备 -> hashcat(GPU)；
   探测命令明确显示只有 CPU -> hashcat(CPU)；此时若 john 可用，auto 改用 john(CPU)；
   hashcat -I 探测失败（不可执行/超时）才退回 engines.json 的 gpu_available 提示值。
3. hashcat 缺失但 john 存在 -> john(CPU)。
4. auto 检测到 GPU 但 hashcat 缺失 -> 回退 john 并给警告。

## engines.json 配置

查找顺序：--engines 指定的路径 > 项目 engines/engines.json > 环境变量 CRUMBS_ENGINES_JSON。

键名约定（全部可选，缺省回退 PATH）：

    {
      "john_run_dir": "C:/crumbs/engines/john/run",
      "john_bin": "C:/crumbs/engines/john/run/john.exe",
      "hashcat_bin": "C:/crumbs/engines/hashcat/hashcat.exe",
      "zip2john": "C:/crumbs/engines/john/run/zip2john.exe",
      "rar2john": "C:/crumbs/engines/john/run/rar2john.exe",
      "sevenz2john": "C:/crumbs/engines/john/run/7z2john.pl",
      "perl_bin": "C:/Strawberry/perl/bin/perl.exe",
      "unrar_bin": "C:/crumbs/engines/unrar/UnRAR.exe",
      "rar_bin": "C:/crumbs/engines/winrar/Rar.exe",
      "sevenz_bin": "C:/Program Files/7-Zip/7z.exe",
      "gpu_available": true,
      "gpu_devices": 1
    }

说明：
- 值可以是绝对路径（原样使用，不要自己拼 .exe）、相对路径（相对 json 所在目录）、
  或裸命令名（在 PATH 中查找）。
- 7z 提取器是 .pl 脚本，运行时会用 perl_bin 执行；perl_bin 缺失时报错退出码 2。
- gpu_available 只在 hashcat -I 探测失败时作为提示值；运行时探测成功时以 -I 结果为准。

## Windows 安装引擎

Python：
- 安装 Python 3.10 以上版本（python.org），勾选 Add python.exe to PATH；
  自带 py 启动器时 crumbs-cracker.bat 会优先用 py -3。

hashcat：
- 从 hashcat.net 下载官方 release 压缩包，解压到例如 C:\crumbs\engines\hashcat；
  主程序是 hashcat.exe。GPU 需要显卡厂商官方驱动。

john-jumbo：
- 下载 john-jumbo 的 Windows 构建（Openwall 官网或社区 release），解压到
  C:\crumbs\engines\john；run 目录下有 john.exe、zip2john.exe、rar2john.exe、
  7z2john.pl。7z2john.pl 需要 Perl（Strawberry Perl 或 ActivePerl）。

7-Zip：
- 7-zip.org 安装 7-Zip，7z.exe 用于 zip/7z 明文复核。

WinRAR / unrar：
- 安装 WinRAR（Rar.exe），或从 rarlab.com 下载 UnRAR.exe，用于 rar 明文复核。

## 常见错误

- "无法识别的压缩格式"：文件头魔术字节不匹配；扩展名改对了也没用，必须换真实格式。
- "提取器未输出可识别哈希"：john-jumbo 提取器未正确安装，或压缩包损坏。
- "hybrid 需要 hashcat，john 无等价攻击模式"：john 没有 -a 6 等价物，换 --engine hashcat。
- "7z 提取器是 perl 脚本，但未找到 perl"：在 engines.json 里配 perl_bin，或把 perl 装进 PATH。
- "未找到可用引擎"：hashcat 和 john 都不在 PATH 里，用 --engines 指定 engines.json。
- 假阳性："[!] 复核未通过" 说明破解器给出的候选密码没能通过 7z/unrar 复核，会被丢弃。
- Windows 控制台乱码：crumbs_cracker.py 已尽量把 stdout/stderr 重配为 utf-8；老 Python 请升到 3.10+。

## 退出码

    0   找到密码（check 成功也是 0）
    1   未找到密码
    2   参数或环境错误（格式无法识别、引擎缺失、参数不完整等）

## 路径里夹带的不可见字符

Windows 上把文件拖进控制台时，路径两侧常被塞进 U+202A/U+202C 之类的双向控制符，
肉眼看不见但会让「文件不存在」误报。crumbs 现在会自动清掉这类字符、零宽字符和首尾引号，
直接把拖拽得到的一整串粘进去即可。

## 组合数上限（2^64）

单次攻击最多约 1.8e19 种（2^64）。逐位尝试时按"单个长度"分别比较——撑得住就继续下一位，
撑不住的那一位起（更长的只会更大）不再尝试，前面的位数照常跑；单轮攻击超限才整单报错。
单轮超限时 crumbs 会在开跑前直接报错（hashcat 原本要到开跑后才报
`Integer overflow detected in keyspace of mask`）：

逐位尝试超限时则是软截断，并提示实际会跑到第几位：

    提示: 10 位起的组合数超出 hashcat 单次上限 2^64≈1.8e19，本次只逐位尝试 1-9 位（…）

    错误: 组合数过大：本次约 1.8e+20 种，超出 hashcat 单次可枚举上限 2^64≈1.8e19；
          请缩短后缀长度或缩小字符集（例如先试 4-6 位），也可改用字典或分几次跑

典型踩坑：混合模式给后缀 10 位、字符集选「全部可打印字符」→ 95^10≈6e19 已超上限。
先试 4-6 位，或用 `--len-min/--len-max` 从短到长逐位试。
