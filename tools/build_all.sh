#!/usr/bin/env bash
# 특수교육 점선체 2종을 만든다.  결과: build/*.ttf, build/web/
#   점선필기체 ← 학교안심 꼬꼬마 R (+ 없는 글자 조립)
#   점선바른체 ← 나눔바른펜 R
# 한글·숫자를 정사각형 따라쓰기 칸 가운데에 맞춤, 점 28 / 간격 56
set -euo pipefail
cd "$(dirname "$0")/.."
VER=${VER:-1.000}
# 일부만 만들려면: ONLY="bareun" ./tools/build_all.sh
ONLY=${ONLY:-"pilgi bareun"}
want() { [[ " $ONLY " == *" $1 "* ]]; }
mkdir -p build

CR_PILGI="Based on Hakgyoansim Kkokkoma (Copyright (c) KERIS; design by Design210). Dotted tracing version (c) 2026 Kim Kyungmin."
CR_BAREUN="Based on NanumBarunPen (Copyright (c) 2010, NAVER Corporation; design by YoonDesign Inc.). Dotted tracing version (c) 2026 Kim Kyungmin."
LIC_OFL="This Font Software is licensed under the SIL Open Font License, Version 1.1."

dotted() {  # 원본 출력 한글이름 영문이름 저작권 [추가옵션...]
  local src=$1 out=$2 ko=$3 en=$4 cr=$5; shift 5
  python3 tools/make_dotted.py "$src" "$out" --version "$VER" --family-ko "$ko" --family-en "$en" \
    --copyright "$cr" --license-text "$LIC_OFL" --license-url "https://openfontlicense.org" "$@"
}

# 필기체: 꼬꼬마에 없는 한글을 조립해 넣은 원본을 먼저 만든다. ㅇ 보정은 필기체에만 쓴다.
if want pilgi; then
  python3 tools/compose_hangul.py 원본/HakgyoansimKkokkomaR.ttf build/src_pilgi.ttf --report build/compose_report.txt
  dotted build/src_pilgi.ttf build/SpecialEdJeomseonPilgi.ttf "특수교육 점선필기체" "Special Ed Jeomseon Pilgi" "$CR_PILGI" \
    --loop-expand 0.9
fi
# 바른체: 획 굵기(약 60)에 맞춰 잔가지 70·꺾임 55
if want bareun; then
  dotted 원본/NanumBarunpenR.ttf build/SpecialEdJeomseonBareun.ttf "특수교육 점선바른체" "Special Ed Jeomseon Bareun" "$CR_BAREUN" \
    --prune 70 --corner-reach 55
fi

for f in build/SpecialEdJeomseon*.ttf; do python3 -m ots "$f" /dev/null >/dev/null && echo "OTS 통과: $f"; done

# 웹 개발용: 한글·숫자·영문·기본 문장부호만 남긴 WOFF2와 CSS
python3 tools/make_web.py build/SpecialEdJeomseon*.ttf --out build/web
ls -l build/SpecialEdJeomseon*.ttf build/web

# 배포 폴더(dist/)에 복사: 설치용 TTF는 한글 파일 이름, 웹폰트는 영어 파일 이름
if [ "${DIST:-0}" = 1 ]; then
  mkdir -p dist/web
  for k in "Pilgi 필기체" "Bareun 바른체"; do
    set -- $k
    [ -f "build/SpecialEdJeomseon$1.ttf" ] && cp "build/SpecialEdJeomseon$1.ttf" "dist/특수교육 점선$2.ttf"
  done
  cp build/web/*.woff2 build/web/fonts.css dist/web/
fi
