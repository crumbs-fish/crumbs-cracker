#!/usr/bin/env bash
set -e
FX=/tmp/crumbs_fx; rm -rf $FX; mkdir -p $FX; cd $FX
echo "hello secret world" > p.txt; echo "second file" > p2.txt
printf 'wrongpass\nletmein\nsecret\n' > words.txt
printf 'wrongpass\nletmein\n' > words_bad.txt
# zip ZipCrypto 单文件 / 双文件 / AES256
7z a -tzip -psecret -mem=ZipCrypto zipcrypto.zip p.txt >/dev/null
7z a -tzip -psecret -mem=AES256 zipaes.zip p.txt >/dev/null
7z a -tzip -psecret -mem=ZipCrypto multi.zip p.txt p2.txt >/dev/null
# 7z 加密头 / 不加密头
7z a -t7z -psecret -mhe=on sevenz.7z p.txt >/dev/null
7z a -t7z -psecret plain7z.7z p.txt >/dev/null
# rar5（rar 7.01）
rar a -idq -psecret rar5.rar p.txt
# rar4（需 rar 6.0.2，7.01 已不支持 -ma4）
if [ ! -x /tmp/rar602/rar/rar ]; then
  mkdir -p /tmp/rar602 && cd /tmp/rar602
  curl -sSL -o rar.tgz https://www.rarlab.com/rar/rarlinux-x64-6.0.2.tar.gz
  tar xzf rar.tgz && rm rar.tgz
  cd $FX
fi
/tmp/rar602/rar/rar a -idq -ma4 -psecret rar4.rar p.txt
# 攻击模式样本
7z a -tzip -p1234 -mem=ZipCrypto mask.zip p.txt >/dev/null
7z a -tzip -psecret42 -mem=ZipCrypto hybrid.zip p.txt >/dev/null
ls -l | awk '{print $5, $9}' | grep -v '^0'
echo "=== 正确密码验证"
7z t -psecret zipcrypto.zip >/dev/null && echo "zipcrypto ok"
7z t -psecret zipaes.zip >/dev/null && echo "zipaes ok"
7z t -psecret multi.zip >/dev/null && echo "multi ok"
7z t -psecret sevenz.7z >/dev/null && echo "sevenz ok"
7z t -psecret plain7z.7z >/dev/null && echo "plain7z ok"
unrar t -psecret rar4.rar >/dev/null && echo "rar4 ok"
unrar t -psecret rar5.rar >/dev/null && echo "rar5 ok"
echo "=== 错误密码必须失败"
! 7z t -pwrong zipcrypto.zip >/dev/null 2>&1 && echo "zipcrypto reject ok"
echo DONE