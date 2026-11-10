#!/usr/bin/env bash
# 원본 폰트를 내려받아 원본/ 에 둔다. 원본 파일은 저장소에 올리지 않는다(.gitignore).
#  - 학교안심 꼬꼬마 R  : npm @kfonts/hakgyoansim-kkokkoma   (KERIS 학교안심폰트)
#  - 나눔바른펜 R       : npm @kfonts/nanum-barun-pen         (네이버, OFL)
#  - 학교안심 오카리나 R: npm 배포본이 없다. 교육저작권지원센터(copyright.keris.or.kr)에서 받아
#                         원본/HakgyoansimOcarinaR.ttf 로 둔다.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p 원본
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

npm_get() {  # 패키지 파일경로 저장이름
  (cd "$tmp" && rm -rf package ./*.tgz && npm pack "$1" --silent >/dev/null && tar xzf ./*.tgz)
  cp "$tmp/package/$2" "원본/$3"
}
[ -f 원본/HakgyoansimKkokkomaR.ttf ] || npm_get @kfonts/hakgyoansim-kkokkoma src/HakgyoansimKkokkomaR.ttf HakgyoansimKkokkomaR.ttf
[ -f 원본/NanumBarunpenR.ttf ] || npm_get @kfonts/nanum-barun-pen src/NanumBarunpenR.ttf NanumBarunpenR.ttf

[ -f 원본/HakgyoansimOcarinaR.ttf ] || echo "주의: 원본/HakgyoansimOcarinaR.ttf 가 없습니다(판서체용). 교육저작권지원센터에서 받아 두세요."
ls -l 원본/
