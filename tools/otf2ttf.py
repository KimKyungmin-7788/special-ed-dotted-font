#!/usr/bin/env python3
"""CFF(OTF) 윤곽 폰트를 TrueType(glyf) 윤곽으로 바꾼다. make_dotted.py 입력용.

    python3 tools/otf2ttf.py IN.otf OUT.ttf
"""
import sys

from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable


def main(src, dst, max_err=1.0):
    font = TTFont(src)
    if "CFF " not in font:
        font.save(dst)
        return
    order = font.getGlyphOrder()
    gs = font.getGlyphSet()
    glyf = newTable("glyf")
    glyf.glyphOrder = order
    glyf.glyphs = {}
    for name in order:
        pen = TTGlyphPen(gs)
        gs[name].draw(Cu2QuPen(pen, max_err, reverse_direction=True))
        glyf[name] = pen.glyph()
    font["glyf"] = glyf
    font["loca"] = newTable("loca")
    del font["CFF "]
    if "VORG" in font:
        del font["VORG"]
    maxp = font["maxp"]
    maxp.tableVersion = 0x00010000
    for k in ("maxZones", "maxTwilightPoints", "maxStorage", "maxFunctionDefs", "maxInstructionDefs",
              "maxStackElements", "maxSizeOfInstructions", "maxComponentElements"):
        setattr(maxp, k, 0)
    maxp.maxZones = 1
    maxp.maxComponentDepth = 0
    font["post"].formatType = 2.0
    font["post"].extraNames = []
    font["post"].mapping = {}
    font["head"].glyphDataFormat = 0
    font.sfntVersion = "\x00\x01\x00\x00"
    font.save(dst)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
