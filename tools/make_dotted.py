#!/usr/bin/env python3
"""가는 손글씨 폰트를 '획 가운데 점선' 따라쓰기 폰트로 바꾼다.

방법
1. 글자를 그림(비트맵)으로 그린 뒤 획의 가운데 선(뼈대)을 뽑는다.
2. 뼈대를 끝점·갈림점·꺾인 곳에서 나눈다.
3. 각 구간마다 양 끝에 점을 찍고, 그 사이를 같은 간격으로 채운다.
   → ㅈ의 7자 꺾임, ㅅ의 갈림점에 항상 점이 찍혀 획의 모양이 살아난다.
4. 점은 'dotmark' 글리프 하나를 만들어 두고 위치만 참조(composite)한다.
   → 파일이 작고, 점 모양·크기를 한 곳에서 바꿀 수 있다.
5. (칸 맞춤) 한글 음절·자모와 숫자는 폭을 1000(정사각형)으로 통일하고, 글자 잉크를 칸 한가운데
   (가로 500, 세로 = 위아래 em의 가운데)에 놓고, 크기를 --box 안에 맞춘다.
   점은 맞춘 뒤에 찍으므로 점 간격은 그대로 고르다.

사용 예
    python3 tools/make_dotted.py 원본/HakgyoansimKkokkomaR.ttf build/proto.ttf
    python3 tools/make_dotted.py SRC OUT --text "자차사" --dot 46 --spacing 95
"""
import argparse
import math
import multiprocessing as mp
import sys

import freetype
import numpy as np
from scipy import ndimage
from skimage.morphology import skeletonize

SCALE = 0.5  # 1000 UPM → 500px. 획 굵기 41 → 약 20px

_face = None
_opts = None


def _init(src, opts):
    global _face, _opts
    _face = freetype.Face(src)
    _face.set_char_size(int(_face.units_per_EM * SCALE * 64), 0, 72, 72)
    _opts = opts


# ---------------------------------------------------------------- 뼈대 추출
def render(gid):
    _face.load_glyph(gid, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
    g = _face.glyph
    b = g.bitmap
    if b.rows == 0 or b.width == 0:
        return None, 0, 0
    a = np.array(b.buffer, dtype=np.uint8).reshape(b.rows, b.pitch)[:, : b.width]
    pad = 2
    a = np.pad(a > 110, pad)
    return a, g.bitmap_left - pad, g.bitmap_top + pad


NB = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def trace_graph(sk):
    """뼈대 픽셀을 구간(polyline) 목록으로 바꾼다. 좌표는 (row, col)."""
    pts = set(zip(*np.nonzero(sk)))
    if not pts:
        return []

    def nbrs(p):
        r, c = p
        return [(r + dr, c + dc) for dr, dc in NB if (r + dr, c + dc) in pts]

    deg = {p: len(nbrs(p)) for p in pts}
    nodes = {p for p in pts if deg[p] != 2}
    edges, used = [], set()

    def walk(start, nxt):
        path = [start, nxt]
        prev, cur = start, nxt
        while cur not in nodes:
            cand = [q for q in nbrs(cur) if q != prev and (cur, q) not in used]
            # 대각선보다 상하좌우 이웃을 먼저 따라간다
            cand.sort(key=lambda q: abs(q[0] - cur[0]) + abs(q[1] - cur[1]))
            if not cand:
                break
            used.add((cur, cand[0]))
            used.add((cand[0], cur))
            prev, cur = cur, cand[0]
            path.append(cur)
            if cur == start:
                break
        return path

    for n in nodes:
        for q in nbrs(n):
            if (n, q) in used:
                continue
            used.add((n, q))
            used.add((q, n))
            edges.append(walk(n, q))
    # 갈림점이 없는 고리(ㅇ 등)
    seen = {p for e in edges for p in e}
    for p in pts:
        if p in seen:
            continue
        q = nbrs(p)
        if not q:
            edges.append([p])
            seen.add(p)
            continue
        used.add((p, q[0]))
        used.add((q[0], p))
        e = walk(p, q[0])
        edges.append(e)
        seen.update(e)
    return edges


def plen(xy):
    if len(xy) < 2:
        return 0.0
    return float(np.sum(np.hypot(*np.diff(xy, axis=0).T)))


def smooth(xy, w):
    if len(xy) < 2 * w + 1:
        return xy
    k = np.ones(2 * w + 1) / (2 * w + 1)
    closed = np.allclose(xy[0], xy[-1])
    if closed:
        ext = np.vstack([xy[-w - 1 : -1], xy, xy[1 : w + 1]])
        out = np.column_stack([np.convolve(ext[:, i], k, "valid") for i in range(2)])
        return out
    out = xy.copy()
    for i in range(2):
        out[w:-w, i] = np.convolve(xy[:, i], k, "valid")
    return out


def corners(xy, reach, min_turn):
    """꺾인 곳의 인덱스. reach 거리 앞뒤 방향을 비교한다."""
    n = len(xy)
    if n < 5:
        return []
    cum = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])
    total = cum[-1]
    turn = np.zeros(n)
    for i in range(n):
        if cum[i] < reach * 0.8 or total - cum[i] < reach * 0.8:
            continue
        a = xy[np.searchsorted(cum, cum[i] - reach)]
        b = xy[min(np.searchsorted(cum, cum[i] + reach), n - 1)]
        v1, v2 = xy[i] - a, b - xy[i]
        n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
        if n1 == 0 or n2 == 0:
            continue
        turn[i] = math.degrees(math.acos(max(-1, min(1, np.dot(v1, v2) / (n1 * n2)))))
    out = []
    i = 0
    while i < n:
        if turn[i] >= min_turn:
            j = i
            while j + 1 < n and turn[j + 1] >= min_turn:
                j += 1
            out.append(i + int(np.argmax(turn[i : j + 1])))
            i = j + 1
        else:
            i += 1
    return out


def expand_round_loop(path, xy, dt, o):
    """닫힌 고리이면서 꺾인 곳이 없는(둥근) 구간이면, 중심에서 바깥쪽으로
    (원래 획 굵기의 절반 × loop_expand)만큼 넓힌다. 굵은 글씨에서 ㅇ이 작아지는 것을 막는다.
    ㅁ·ㅂ처럼 모서리가 있는 고리, 열린 획은 그대로 둔다."""
    if len(path) < 12 or max(abs(path[0][0] - path[-1][0]), abs(path[0][1] - path[-1][1])) > 3:
        return xy  # 닫힌 고리가 아님 (갈림점 덩어리 때문에 양 끝이 몇 픽셀 떨어진 경우는 닫힌 것으로 봄)
    sm = smooth(xy, 3)
    # 둥근지 판단: 둘레의 1/12 거리 앞뒤로 방향이 65° 넘게 꺾이는 곳이 있으면 모서리 있는 고리(ㅁ·ㅂ)로 본다.
    # 실측(나눔바른펜·꼬꼬마 등): ㅇ은 최대 38~59°, ㅁ은 69~90°. ㅇ의 펜 시작점 꺾임은 65° 미만.
    if corners(sm, plen(sm) / 12, 65):
        return xy
    half = float(np.median([dt[p] for p in path])) / SCALE  # 획 굵기의 절반(1000 기준)
    c = xy[:-1].mean(axis=0)
    r = float(np.mean(np.hypot(*(xy - c).T)))
    if r <= 0:
        return xy
    k = 1 + o.loop_expand * half / r
    return c + (xy - c) * k


def dots_for_glyph(gid):
    o = _opts
    a, left, top = render(gid)
    if a is None or not a.any():
        return gid, []
    a = ndimage.binary_closing(a, iterations=1)
    sk = skeletonize(a)
    edges = trace_graph(sk)

    def to_units(path):
        rc = np.array(path, dtype=float)
        x = (left + rc[:, 1] + 0.5) / SCALE
        y = (top - rc[:, 0] - 0.5) / SCALE
        return np.column_stack([x, y])

    polys = [to_units(e) for e in edges]
    if o.loop_expand > 0:  # ㅇ처럼 둥근 고리를 원래 획 바깥쪽으로 넓힌다
        dt = ndimage.distance_transform_edt(a)
        polys = [expand_round_loop(e, xy, dt, o) for e, xy in zip(edges, polys)]
    if gid in o.norm:  # 칸 맞춤: 잉크 중심을 칸 중심으로, 크기를 맞춤
        s, cx, cy = o.norm[gid]
        polys = [np.column_stack([(xy[:, 0] - cx) * s + o.cell_cx, (xy[:, 1] - cy) * s + o.cell_cy]) for xy in polys]
    # 짧은 가시(뼈대 끝의 잔가지) 제거: 한쪽 끝이 막다른 길이고 짧으면 버린다
    ends = {}
    for e in edges:
        for p in (e[0], e[-1]):
            ends[p] = ends.get(p, 0) + 1
    keep = []
    for e, xy in zip(edges, polys):
        dead = ends[e[0]] == 1 or ends[e[-1]] == 1
        branchy = ends[e[0]] > 1 or ends[e[-1]] > 1
        if dead and branchy and plen(xy) < o.prune:
            continue
        keep.append(xy)

    fixed, free = [], []  # fixed: 끝점·갈림점·꺾임(우선), free: 중간 채움
    for xy in keep:
        if len(xy) == 1 or plen(xy) < o.dot * 0.6:
            fixed.append(xy.mean(axis=0))
            continue
        xy = smooth(xy, 2)
        cut = [0] + corners(xy, o.corner_reach, o.corner_angle) + [len(xy) - 1]
        cum = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])
        for s, t in zip(cut[:-1], cut[1:]):
            L = cum[t] - cum[s]
            fixed.append(xy[s])
            fixed.append(xy[t])
            k = max(1, int(round(L / o.spacing)))
            for i in range(1, k):
                d = cum[s] + L * i / k
                j = int(np.searchsorted(cum, d))
                j = min(max(j, 1), len(xy) - 1)
                f = (d - cum[j - 1]) / max(cum[j] - cum[j - 1], 1e-9)
                free.append(xy[j - 1] + f * (xy[j] - xy[j - 1]))

    out = []
    min_d = o.spacing * o.merge
    for p in fixed + free:
        if all(math.hypot(p[0] - q[0], p[1] - q[1]) >= min_d for q in out):
            out.append(p)
    if gid in o.norm and out:  # 칸 맞춤: 마지막으로 점들의 범위가 칸 한가운데 오도록 다시 맞춘다
        xs, ys = [p[0] for p in out], [p[1] for p in out]
        dx = o.cell_cx - (min(xs) + max(xs)) / 2
        dy = o.cell_cy - (min(ys) + max(ys)) / 2
        out = [(x + dx, y + dy) for x, y in out]
    return gid, [(int(round(x)), int(round(y))) for x, y in out]


# ---------------------------------------------------------------- 폰트 쓰기
def build(src, dst, gids_dots, opts):
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib import TTFont
    from fontTools.ttLib.tables._g_l_y_f import GlyphComponent, Glyph

    font = TTFont(src)
    glyf, hmtx = font["glyf"], font["hmtx"]
    order = font.getGlyphOrder()

    # 점 글리프 (원)
    r = opts.dot / 2
    pen = TTGlyphPen(None)
    R = r / math.cos(math.pi / 8)
    offs = [(R * math.cos(math.radians(22.5 + 45 * k)), R * math.sin(math.radians(22.5 + 45 * k))) for k in range(8)]
    pen.qCurveTo(*[(round(x), round(y)) for x, y in offs], None)
    pen.closePath()
    dot = pen.glyph()
    order.append("dotmark")
    font.setGlyphOrder(order)
    glyf.glyphOrder = order
    glyf["dotmark"] = dot
    hmtx["dotmark"] = (0, 0)

    for gid, dots in gids_dots.items():
        name = order[gid]
        g = Glyph()
        if dots:
            g.numberOfContours = -1
            g.components = []
            for x, y in dots:
                c = GlyphComponent()
                c.glyphName = "dotmark"
                c.x, c.y = x, y
                c.flags = 0x4  # ROUND_XY_TO_GRID
                g.components.append(c)
        else:
            g.numberOfContours = 0
        glyf[name] = g
        g.recalcBounds(glyf)
        adv, _ = hmtx[name]
        if gid in opts.norm:
            adv = opts.square
        hmtx[name] = (adv, getattr(g, "xMin", 0))

    # 원본에 그려지지 않은(빈) 한글 음절은 cmap에서 뺀다.
    # 빈 칸으로 보이는 대신 워드프로세서가 다른 폰트로 대체해 보여 주므로 누락을 알아챌 수 있다.
    if opts.drop_empty_hangul and not opts.text:
        empty = {n for n in order if n != "dotmark" and glyf[n].numberOfContours == 0}
        for t in font["cmap"].tables:
            if t.isUnicode():
                t.cmap = {k: v for k, v in t.cmap.items() if not (0xAC00 <= k <= 0xD7A3 and v in empty)}

    for tag in ("fpgm", "prep", "cvt ", "hdmx", "LTSH", "VDMX", "DSIG"):
        if tag in font:
            del font[tag]
    font["maxp"].maxZones = 1
    if "gasp" in font:
        font["gasp"].gaspRange = {0xFFFF: 0x000F}

    if opts.color:
        add_color(font, gids_dots, opts.color)

    if opts.fstype is not None:  # 문서 포함(임베딩) 허용 범위
        font["OS/2"].fsType = opts.fstype
    if opts.unify_metrics:
        unify_metrics(font, opts)
    set_names(font, opts)
    font.save(dst)


def unify_metrics(font, opts):
    """여러 폰트가 같은 칸에서 같은 자리에 오도록 줄 높이 정보를 통일한다.
    hhea·typo: 위 opts.asc / 아래 opts.desc, 줄 간격 0. win: 잘림 방지를 위해 실제 글자 범위까지."""
    glyf = font["glyf"]
    ymax, ymin = opts.asc, opts.desc
    for n in font.getGlyphOrder():
        g = glyf[n]
        if g.numberOfContours != 0 and hasattr(g, "yMax"):
            ymax, ymin = max(ymax, g.yMax), min(ymin, g.yMin)
    h, o = font["hhea"], font["OS/2"]
    h.ascent, h.descent, h.lineGap = opts.asc, opts.desc, 0
    o.sTypoAscender, o.sTypoDescender, o.sTypoLineGap = opts.asc, opts.desc, 0
    o.usWinAscent, o.usWinDescent = int(ymax), int(-ymin)
    if o.version < 4:  # USE_TYPO_METRICS 비트는 OS/2 버전 4부터
        o.version = 4
    o.fsSelection |= 1 << 7  # USE_TYPO_METRICS


def add_color(font, gids_dots, hexcolor):
    """COLR v0 + CPAL로 점 글자의 기본색을 정한다.
    색 폰트를 지원하는 프로그램(웹 브라우저, 최신 MS Office 등)에서만 이 색으로 보이고,
    지원하지 않는 프로그램에서는 평소처럼 글자색(보통 검정)으로 보인다."""
    from fontTools.colorLib.builder import buildCOLR, buildCPAL

    h = hexcolor.lstrip("#")
    rgba = tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)) + (1.0,)
    order = font.getGlyphOrder()
    layers = {order[gid]: [(order[gid], 0)] for gid, dots in gids_dots.items() if dots}
    font["CPAL"] = buildCPAL([[rgba]])
    font["COLR"] = buildCOLR(layers, version=0)


def set_names(font, opts):
    name = font["name"]
    fam_en, fam_ko = opts.family_en, opts.family_ko
    ps = fam_en.replace(" ", "") + "-Regular"
    copyright_ = opts.copyright
    keep = {0, 1, 2, 3, 4, 5, 6, 9, 13, 14, 16, 17}
    # 윈도우용(platformID 3) 이름만 남긴다. 다른 플랫폼 기록에 원본 폰트 이름이 남지 않게 한다.
    name.names = [n for n in name.names if n.platformID == 3 and n.nameID in keep - {16, 17}]
    for lang, fam in ((0x409, fam_en), (0x412, fam_ko)):
        name.setName(copyright_, 0, 3, 1, lang)
        name.setName(fam, 1, 3, 1, lang)
        name.setName("Regular", 2, 3, 1, lang)
        name.setName(f"{opts.version};{ps}", 3, 3, 1, lang)
        name.setName(fam, 4, 3, 1, lang)
        name.setName(f"Version {opts.version}", 5, 3, 1, lang)
        name.setName(ps, 6, 3, 1, lang)
        name.setName(opts.license_text, 13, 3, 1, lang)
        designer = opts.designer_ko if lang == 0x412 else opts.designer_en
        if designer:
            name.setName(designer, 9, 3, 1, lang)  # 디자이너(개발자)
    name.removeNames(nameID=14)
    if opts.license_url:
        for lang in (0x409, 0x412):
            name.setName(opts.license_url, 14, 3, 1, lang)
    font["head"].fontRevision = float(opts.version)


def in_grid(cp, opts):
    """칸 맞춤 대상 글자인가: 한글 음절, 호환 자모, (기본) 숫자 0-9와 전각 숫자."""
    if 0xAC00 <= cp <= 0xD7A3 or 0x3131 <= cp <= 0x318E:
        return True
    return opts.grid_digits and (0x30 <= cp <= 0x39 or 0xFF10 <= cp <= 0xFF19)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--text", help="이 글자들만 변환(미리보기용). 지정하지 않으면 모든 글리프")
    ap.add_argument("--dot", type=float, default=28, help="점 지름(1000 기준)")
    ap.add_argument("--spacing", type=float, default=56, help="점 중심 간격")
    ap.add_argument("--merge", type=float, default=0.55, help="이 비율×간격보다 가까운 점은 하나로")
    ap.add_argument("--prune", type=float, default=45, help="이보다 짧은 잔가지 제거")
    ap.add_argument("--corner-angle", type=float, default=45, help="이 각도 이상 꺾이면 꺾임점")
    ap.add_argument("--loop-expand", type=float, default=0.0,
                    help="둥근 고리(ㅇ)를 획 굵기 절반의 몇 배만큼 바깥으로 넓힐지 (0=안 함). 굵은 원본에 0.8 정도")
    ap.add_argument("--corner-reach", type=float, default=40, help="꺾임 판정 거리")
    ap.add_argument("--family-en", default="Special Ed Jeomseon")
    ap.add_argument("--family-ko", default="특수교육 점선체")
    ap.add_argument("--version", default="1.000")
    ap.add_argument("--copyright", default="Dotted tracing derivative, 2026.", help="name ID 0 저작권 문구")
    ap.add_argument("--fstype", type=int, default=None, help="OS/2 fsType(임베딩 허용). 예: 8=편집 가능 임베딩")
    ap.add_argument("--designer-ko", default="김경민", help="name ID 9 개발자 이름(한국어)")
    ap.add_argument("--designer-en", default="Kim Kyungmin", help="name ID 9 개발자 이름(영어)")
    ap.add_argument("--license-url", default="", help="name ID 14 라이선스 주소")
    ap.add_argument("--asc", type=int, default=800, help="통일할 위 높이")
    ap.add_argument("--desc", type=int, default=-200, help="통일할 아래 깊이(음수)")
    ap.add_argument("--keep-metrics", dest="unify_metrics", action="store_false",
                    help="원본의 줄 높이 정보를 그대로 둔다")
    ap.add_argument(
        "--license-text",
        default="Free to use and redistribute; not for sale as a font file.",
    )
    ap.add_argument("--color", default="#6B6A6A",
                    help="색 폰트(COLR) 기본색. 빈 문자열이면 색 정보 없이 만든다")
    ap.add_argument("--keep-empty-hangul", dest="drop_empty_hangul", action="store_false",
                    help="원본에 없는(빈) 한글 음절도 cmap에 남긴다")
    ap.add_argument("--no-grid-fit", dest="grid_fit", action="store_false",
                    help="한글을 정사각형 칸에 맞추지 않고 원본 위치·크기 그대로 둔다")
    ap.add_argument("--no-grid-digits", dest="grid_digits", action="store_false",
                    help="숫자는 칸에 맞추지 않고 원본(좁은 폭, 기준선 위치) 그대로 둔다")
    ap.add_argument("--box", type=float, default=800, help="칸 맞춤: 글자 잉크가 들어갈 정사각형 크기")
    ap.add_argument("--min-scale", type=float, default=0.6, help="칸 맞춤: 최소 배율")
    ap.add_argument("--max-scale", type=float, default=1.25, help="칸 맞춤: 최대 배율(간단한 글자가 너무 커지지 않게)")
    ap.add_argument("-j", "--jobs", type=int, default=mp.cpu_count())
    opts = ap.parse_args()

    from fontTools.ttLib import TTFont

    f = TTFont(opts.src)
    if "CFF " in f:  # OTF(CFF) 원본은 TrueType 윤곽으로 바꿔서 쓴다
        import os
        import tempfile

        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from otf2ttf import main as otf2ttf

        tmp = os.path.join(tempfile.mkdtemp(), "src.ttf")
        otf2ttf(opts.src, tmp)
        opts.src = tmp
        f = TTFont(tmp)
    order = f.getGlyphOrder()
    glyf = f["glyf"]
    if opts.text:
        cmap = f.getBestCmap()
        gids = sorted({f.getGlyphID(cmap[ord(ch)]) for ch in opts.text if ord(ch) in cmap})
    else:
        gids = [i for i, n in enumerate(order) if glyf[n].numberOfContours != 0]
    # 칸 맞춤 대상: 한글 음절 + 호환 자모
    opts.norm = {}
    upm = f["head"].unitsPerEm
    opts.square = upm
    opts.cell_cx = upm / 2
    if opts.unify_metrics:
        opts.cell_cy = (opts.asc + opts.desc) / 2  # 800, -200 → 300
    else:
        opts.cell_cy = (f["hhea"].ascent + f["hhea"].descent) / 2
    if opts.grid_fit:
        from fontTools.pens.boundsPen import BoundsPen

        gs = f.getGlyphSet()
        want = set(gids)
        for k, n in f.getBestCmap().items():
            if not in_grid(k, opts):
                continue
            gid = f.getGlyphID(n)
            if gid not in want:
                continue
            bp = BoundsPen(gs)
            gs[n].draw(bp)
            if not bp.bounds:
                continue
            x0, y0, x1, y1 = bp.bounds
            sc = opts.box / max(x1 - x0, y1 - y0)
            sc = min(max(sc, opts.min_scale), opts.max_scale)
            opts.norm[gid] = (sc, (x0 + x1) / 2, (y0 + y1) / 2)
    del f

    print(f"{len(gids)}개 글리프 변환 중…", file=sys.stderr)
    res = {}
    with mp.Pool(opts.jobs, initializer=_init, initargs=(opts.src, opts)) as pool:
        for i, (gid, dots) in enumerate(pool.imap_unordered(dots_for_glyph, gids, chunksize=32), 1):
            res[gid] = dots
            if i % 1000 == 0:
                print(f"  {i}/{len(gids)}", file=sys.stderr)
    build(opts.src, opts.dst, res, opts)
    n = sum(len(v) for v in res.values())
    print(f"완료: {opts.dst} (점 {n}개, 글자당 평균 {n / max(len(res), 1):.1f}개)", file=sys.stderr)


if __name__ == "__main__":
    main()
