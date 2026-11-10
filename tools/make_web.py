#!/usr/bin/env python3
"""웹사이트·웹앱 개발용 파일을 만든다: 글자를 줄인 WOFF2 + CSS(@font-face).

남기는 글자: 한글 음절·호환 자모, 기본 라틴(영문·숫자·기호), 전각 숫자, 자주 쓰는 문장부호.
한자 등은 빼서 파일을 작게 한다(TTF 4.7~7.7MB → WOFF2 수백 KB~1MB대).

    python3 tools/make_web.py build/SpecialEdJeomseon*.ttf --out build/web
"""
import argparse
import os

from fontTools import subset
from fontTools.ttLib import TTFont

UNICODES = (
    list(range(0x20, 0x7F))
    + list(range(0xAC00, 0xD7A4))
    + list(range(0x3131, 0x318F))
    + list(range(0xFF10, 0xFF1A))
    + [0xA0, 0xB7, 0x2018, 0x2019, 0x201C, 0x201D, 0x2026, 0x3001, 0x3002, 0x300C, 0x300D]
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fonts", nargs="+")
    ap.add_argument("--out", default="build/web")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    css = []
    for src in a.fonts:
        f = TTFont(src)
        fam_ko = str(f["name"].getName(1, 3, 1, 0x412) or f["name"].getName(1, 3, 1, 0x409))
        fam_en = str(f["name"].getName(1, 3, 1, 0x409))
        base = os.path.splitext(os.path.basename(src))[0]
        opts = subset.Options()
        opts.flavor = "woff2"
        opts.layout_features = ["*"]
        opts.name_IDs = ["*"]
        opts.name_languages = ["*"]
        opts.notdef_outline = True
        opts.drop_tables = []
        sub = subset.Subsetter(opts)
        sub.populate(unicodes=UNICODES)
        sub.subset(f)
        out = os.path.join(a.out, base + ".woff2")
        subset.save_font(f, out, opts)
        print(f"{out}  {os.path.getsize(out) // 1024} KB")
        css.append(
            f"/* {fam_ko} */\n@font-face {{\n  font-family: '{fam_ko}';\n"
            f"  src: url('./{base}.woff2') format('woff2');\n"
            f"  font-weight: normal;\n  font-style: normal;\n  font-display: swap;\n}}\n"
        )
    with open(os.path.join(a.out, "fonts.css"), "w") as fh:
        fh.write("/* 특수교육 점선체 웹폰트. 사용 예: font-family: '특수교육 점선필기체'; */\n\n" + "\n".join(css))
    print(os.path.join(a.out, "fonts.css"))


if __name__ == "__main__":
    main()
