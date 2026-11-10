#!/usr/bin/env python3
"""원본에 없는 한글 음절을, 원본에 있는 음절의 조각을 이어 붙여 만든다(윤곽 단계).

원리 (받침 있는 음절 L+V+T를 만들 때)
- 윗부분(초성+중성): 같은 L+V에 받침이 있는 음절 A에서 받침을 떼어 낸 나머지
  (없으면 같은 L+V의 받침 없는 음절을 윗자리 크기로 줄여서 사용)
- 받침: 같은 V(없으면 같은 모양의 모음, 그것도 없으면 아무 모음)와 같은 T를 가진 음절 B에서 떼어 낸 받침
- 받침 위치: B에서 '윗부분과 받침 사이 간격'과 '가로 중심 차이'를 그대로 옮긴다.

받침 떼어 내기: 음절을 이어진 조각(구멍 포함)으로 나누고, 어떤 조각도 걸치지 않는
가로선 중 아래쪽 조각 묶음의 높이가 그 받침의 보통 높이에 가장 가까운 선에서 자른다.
윗부분과 받침이 붙어 있어 자를 수 없는 음절은 재료로 쓰지 않는다.

    python3 tools/compose_hangul.py 원본/HakgyoansimKkokkomaR.ttf build/source_extended.ttf
결과 폰트는 원본 글씨체 그대로(채움 글자)이며, make_dotted.py의 입력으로 쓴다.
"""
import argparse
import sys
from collections import Counter, defaultdict
from statistics import median

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

S0 = 0xAC00
VERT = {0, 1, 2, 3, 4, 5, 6, 7, 20}  # ㅏㅐㅑㅒㅓㅔㅕㅖㅣ
HORI = {8, 12, 13, 17, 18}  # ㅗㅛㅜㅠㅡ
DOUBLE_L = {1, 4, 8, 10, 13}  # ㄲㄸㅃㅆㅉ
WIDE_T = {2, 3, 5, 6, 9, 10, 11, 12, 13, 14, 15, 18, 20}  # ㄲㄳㄵㄶㄺㄻㄼㄽㄾㄿㅀㅄㅆ


def vcls(v):
    return "V" if v in VERT else "H" if v in HORI else "M"


def dec(cp):
    i = cp - S0
    return i // 588, (i % 588) // 28, i % 28


def enc(l, v, t):
    return S0 + l * 588 + v * 28 + t


# ------------------------------------------------------------------ 윤곽 다루기
def contours_of(gs, name):
    rec = RecordingPen()
    gs[name].draw(rec)
    out, cur = [], []
    for op, args in rec.value:
        cur.append((op, args))
        if op in ("closePath", "endPath"):
            out.append(cur)
            cur = []
    return out


def cbounds(c):
    pts = [p for _, args in c for p in args]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def area(c):
    pts = [p for _, args in c for p in args]
    return sum(pts[i][0] * pts[i - 1][1] - pts[i - 1][0] * pts[i][1] for i in range(len(pts))) / 2


def components(contours):
    """구멍(안쪽 윤곽)을 바깥 윤곽에 묶어 '이어진 조각' 목록으로. 각 조각 = (윤곽들, bbox)."""
    info = [(c, cbounds(c), abs(area(c))) for c in contours]
    info.sort(key=lambda x: -x[2])
    comps = []
    for c, b, _ in info:
        for comp in comps:
            ob = comp[1]
            if b[0] >= ob[0] and b[1] >= ob[1] and b[2] <= ob[2] and b[3] <= ob[3]:
                comp[0].append(c)
                break
        else:
            comps.append([[c], b])
    return comps


def union_b(bs):
    return min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs)


def splits(comps):
    """어떤 조각도 걸치지 않는 가로선으로 나눈 (위, 아래) 후보들."""
    ys = sorted(comps, key=lambda c: c[1][1])
    out = []
    for s in sorted({c[1][3] for c in comps}):
        below = [c for c in comps if c[1][3] <= s]
        above = [c for c in comps if c[1][1] > s]
        if below and above and len(below) + len(above) == len(comps):
            out.append((above, below))
    return out


def split_glyph(comps, want=None):
    """want = (조각 수, 높이, 폭) 받침의 보통 모양. 없으면 틈이 가장 큰 곳에서 자른다."""
    cands = splits(comps)
    if not cands:
        return None
    if want is None:  # 첫 추정: 위아래 사이 틈이 가장 큰 곳
        def gap(c):
            return union_b([x[1] for x in c[0]])[1] - union_b([x[1] for x in c[1]])[3]
        return max(cands, key=gap)
    n, h, w = want
    ok = []
    for c in cands:
        b = union_b([x[1] for x in c[1]])
        bh, bw = b[3] - b[1], b[2] - b[0]
        # 조각 수가 같고, 높이·폭이 보통 받침의 0.65~1.5배 안일 때만 받침으로 인정
        if len(c[1]) == n and 0.65 * h <= bh <= 1.5 * h and 0.65 * w <= bw <= 1.5 * w:
            ok.append((abs(bh - h) / h + abs(bw - w) / w, c))
    if not ok:
        return None
    return min(ok, key=lambda x: x[0])[1]


# ------------------------------------------------------------------ 조립
def draw_comps(pen, comps, dx=0, dy=0, sx=1, sy=1, ox=0, oy=0):
    """조각들을 (ox,oy) 기준으로 sx,sy 배율 후 dx,dy 이동해 그린다."""
    tp = TransformPen(pen, (sx, 0, 0, sy, dx + ox - ox * sx, dy + oy - oy * sy))
    for comp in comps:
        for c in comp[0]:
            for op, args in c:
                getattr(tp, op)(*args)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--report", help="만든 글자 목록을 저장할 텍스트 파일")
    a = ap.parse_args()

    font = TTFont(a.src)
    gs = font.getGlyphSet()
    cmap = font.getBestCmap()
    glyf, hmtx = font["glyf"], font["hmtx"]

    drawn = {}
    for cp in range(S0, 0xD7A4):
        n = cmap.get(cp)
        if n is None:
            continue
        bp = BoundsPen(gs)
        gs[n].draw(bp)
        if bp.bounds:
            drawn[cp] = components(contours_of(gs, n))

    # 1차: 받침의 보통 모양(조각 수·높이·폭) 추정 → 2차: 그 모양에 맞는 자리에서만 자르기
    first = defaultdict(list)
    for cp, comps in drawn.items():
        l, v, t = dec(cp)
        if t:
            sp = split_glyph(comps)
            if sp:
                b = union_b([x[1] for x in sp[1]])
                first[t].append((len(sp[1]), b[3] - b[1], b[2] - b[0]))
    want = {}
    for t, rows in first.items():
        n = Counter(r[0] for r in rows).most_common(1)[0][0]
        same = [r for r in rows if r[0] == n]
        want[t] = (n, median(r[1] for r in same), median(r[2] for r in same))
    parts = {}  # cp -> (top comps, bottom comps)
    for cp, comps in drawn.items():
        l, v, t = dec(cp)
        if t and t in want:
            sp = split_glyph(comps, want[t])
            if sp:
                parts[cp] = sp
    # 윗부분(초성+중성)의 보통 크기: 모음 모양 갈래별
    top_h = defaultdict(list)
    for cp, (top, bot) in parts.items():
        b = union_b([x[1] for x in top])
        top_h[vcls(dec(cp)[1])].append(b[3] - b[1])
    top_h = {k: median(v) for k, v in top_h.items()}
    # 원본 글자 전체 높이의 범위(검사용)
    heights = sorted(union_b([x[1] for x in c])[3] - union_b([x[1] for x in c])[1] for c in drawn.values())
    max_h = heights[int(len(heights) * 0.98)] * 1.03
    ymin_ok = min(union_b([x[1] for x in c])[1] for c in drawn.values()) - 20

    by_lv = defaultdict(list)  # (l,v) -> [cp with 받침]
    by_t = defaultdict(list)  # t -> [cp]
    for cp in parts:
        l, v, t = dec(cp)
        by_lv[(l, v)].append(cp)
        by_t[t].append(cp)

    def pick_top(l, v, t):
        c = by_lv.get((l, v))
        if not c:
            return None
        return min(c, key=lambda cp: ((dec(cp)[2] in WIDE_T) != (t in WIDE_T), abs(want[dec(cp)[2]][1] - want[t][1])))

    def pick_bottom(l, v, t):
        c = by_t.get(t)
        if not c:
            return None

        def key(cp):
            L, V, _ = dec(cp)
            return (V != v, vcls(V) != vcls(v), (L in DOUBLE_L) != (l in DOUBLE_L), L != l)
        return min(c, key=key)

    made, how, fail = {}, defaultdict(int), []
    for cp in range(S0, 0xD7A4):
        if cp in drawn:
            continue
        l, v, t = dec(cp)
        if t == 0:
            fail.append(cp)
            continue
        B = pick_bottom(l, v, t)
        if B is None:
            fail.append(cp)
            continue
        btop, bbot = parts[B]
        bt, bb = union_b([x[1] for x in btop]), union_b([x[1] for x in bbot])
        gap = bt[1] - bb[3]
        pen = TTGlyphPen(None)
        A = pick_top(l, v, t)
        if A is not None:
            top = parts[A][0]
            tb = union_b([x[1] for x in top])
            draw_comps(pen, top)
            adv = hmtx[cmap[A]][0]
            how["윗부분: 같은 초성+중성(받침 있는 글자)"] += 1
        elif enc(l, v, 0) in drawn:
            # 받침 없는 L+V 글자를 B의 윗부분 자리 크기로 줄인다
            src = drawn[enc(l, v, 0)]
            sb = union_b([x[1] for x in src])
            # 세로는 같은 모음 갈래의 '받침 있는 윗부분' 보통 높이로, 가로는 조금만 줄인다
            sy = min(1.0, top_h[vcls(v)] / (sb[3] - sb[1]))
            sx = min(1.0, max(sy, 0.9))
            if sy < 0.6:
                fail.append(cp)
                continue
            dx = (bt[0] + bt[2]) / 2 - (sb[0] + sb[2]) / 2
            dy = bt[3] - (sb[1] + (sb[3] - sb[1]) * sy)  # 윗선을 B 윗부분의 윗선에 맞춤
            draw_comps(pen, src, dx, dy, sx, sy, (sb[0] + sb[2]) / 2, sb[1])
            w, h = (sb[2] - sb[0]) * sx, (sb[3] - sb[1]) * sy
            cx = (sb[0] + sb[2]) / 2 + dx
            tb = (cx - w / 2, bt[3] - h, cx + w / 2, bt[3])
            adv = hmtx[cmap[enc(l, v, 0)]][0]
            how["윗부분: 받침 없는 같은 초성+중성을 줄임"] += 1
        else:
            fail.append(cp)
            continue
        # 받침: B에서의 간격·가로 중심 차이를 유지
        dx = ((tb[0] + tb[2]) / 2 - (bt[0] + bt[2]) / 2)
        dy = (tb[1] - gap) - bb[3]
        draw_comps(pen, bbot, dx, dy)
        g = pen.glyph()
        # 검사: 전체 높이와 아래 끝이 원본 글자들의 범위 안이어야 한다
        lo = bb[1] + dy
        if (tb[3] - lo) > max_h or lo < ymin_ok:
            fail.append(cp)
            how["검사 탈락"] += 1
            continue
        made[cp] = (g, adv)
        V = dec(B)[1]
        how["받침: " + ("같은 중성" if V == v else "같은 모양 모음" if vcls(V) == vcls(v) else "다른 모음")] += 1

    for cp, (g, adv) in made.items():
        name = cmap[cp]
        glyf[name] = g
        g.recalcBounds(glyf)
        hmtx[name] = (adv, g.xMin)
    font.save(a.dst)

    print(f"원본에 있던 한글 {len(drawn)}자, 받침 분리 성공 {len(parts)}자", file=sys.stderr)
    print(f"새로 만든 글자 {len(made)}자, 못 만든 글자 {len(fail)}자", file=sys.stderr)
    for k, n in sorted(how.items()):
        print(f"  {k}: {n}", file=sys.stderr)
    if a.report:
        with open(a.report, "w") as fh:
            fh.write("# 새로 만든 글자\n" + "".join(chr(c) for c in sorted(made)) + "\n")
            fh.write("# 못 만든 글자\n" + "".join(chr(c) for c in fail) + "\n")


if __name__ == "__main__":
    main()
