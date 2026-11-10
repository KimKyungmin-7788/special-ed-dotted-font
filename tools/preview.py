#!/usr/bin/env python3
"""점선 폰트 미리보기 그림을 만든다.

    python3 tools/preview.py build/proto.ttf out.png --text "자차사" [--under 원본.ttf]

--under 를 주면 원본 글자를 연한 회색으로 깔고 그 위에 점선을 그린다(점 위치 점검용).
각 줄은 공백 없이 한 칸(정사각형 칸)씩 그린다. '/'는 줄바꿈.
"""
import argparse

from PIL import Image, ImageDraw, ImageFont


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("font")
    ap.add_argument("out")
    ap.add_argument("--text", required=True)
    ap.add_argument("--under")
    ap.add_argument("--size", type=int, default=160)
    ap.add_argument("--color", default="#000000", help="점 색(예: #888888)")
    ap.add_argument("--grid", action="store_true", help="따라쓰기 칸(십자 보조선) 그리기")
    a = ap.parse_args()

    lines = a.text.split("/")
    cell = int(a.size * 1.15)
    W = cell * max(len(l) for l in lines) + 40
    H = cell * len(lines) + 40
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(a.font, a.size)
    u = ImageFont.truetype(a.under, a.size) if a.under else None
    for r, line in enumerate(lines):
        for c, ch in enumerate(line):
            x, y = 20 + c * cell, 20 + r * cell
            if a.grid:
                d.rectangle((x, y, x + cell - 1, y + cell - 1), outline=(200, 160, 160))
                d.line((x + cell // 2, y, x + cell // 2, y + cell), fill=(235, 210, 210))
                d.line((x, y + cell // 2, x + cell, y + cell // 2), fill=(235, 210, 210))
            # 글자 폭(advance) 기준 가로 가운데, 기준선은 칸 위에서 em의 80% 지점
            ox = x + (cell - d.textlength(ch, font=f)) / 2
            asc, desc = f.getmetrics()  # 줄 상자(위·아래)의 가운데를 칸 가운데에
            base = y + cell / 2 + (asc - desc) / 2
            if u:
                d.text((ox, base), ch, font=u, fill=(205, 205, 205), anchor="ls")
            if u:
                d.text((ox, base), ch, font=f, fill=(220, 40, 40), anchor="ls")
            else:
                # 색 폰트(COLR)면 폰트에 든 색으로 그린다
                d.text((ox, base), ch, font=f, fill=a.color, anchor="ls", embedded_color=True)
    img.save(a.out)


if __name__ == "__main__":
    main()
