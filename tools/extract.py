#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
くみたてる — データ抽出

KanjiVG (CC BY-SA 3.0 / http://kanjivg.tagaini.net) から
ゲームが読む JSON を作る。

  python3 tools/extract.py --verify            外接矩形の検算だけ
  python3 tools/extract.py --survey            粒度 2/3/4 の比較
  python3 tools/extract.py --out data/kumitateru.json --min-strokes 2
"""

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
KDIR = os.path.join(ROOT, "kanjivg", "kanji")
SVG = "{http://www.w3.org/2000/svg}"


# ───────────────────────── SVG の読み込み ─────────────────────────

_docs = {}


def load(ch):
    """1文字ぶんの KanjiVG SVG のルート要素。無ければ None"""
    if ch in _docs:
        return _docs[ch]
    root = None
    if len(ch) == 1:
        p = os.path.join(KDIR, "%05x.svg" % ord(ch))
        if os.path.exists(p):
            txt = open(p, encoding="utf-8").read()
            # 内部DTDを消さないと xml.etree がコケる
            txt = re.sub(r"<!DOCTYPE.*?\]>", "", txt, flags=re.S)
            # kvg: 名前空間を扱いやすい属性名にする
            txt = txt.replace("kvg:", "kvg_")
            root = ET.fromstring(txt)
    _docs[ch] = root
    return root


def stroke_root(root):
    """StrokePaths グループの中身（＝字そのもの）。
    StrokeNumbers（画数の数字テキスト）は含めない。
    ※ id は kvg: を kvg_ に置換した影響で変わるので部分一致で見る"""
    if root is None:
        return None
    for g in root.iter(SVG + "g"):
        if "StrokePaths" in g.get("id", ""):
            kids = list(g)
            return kids[0] if kids else None
    return None


def paths_of(node):
    """node の下にある全ての画（d 属性）を文書順で"""
    return [p.get("d") for p in node.iter(SVG + "path") if p.get("d")]


# ───────────────────────── 外接矩形 ─────────────────────────


def bbox(ds):
    """d 属性のリストから外接矩形 [x0,y0,x1,y1]。
    ベジェの制御点も含めるのでわずかに大きめに出るが実用上は問題ない"""
    xs, ys = [], []
    for d in ds:
        cx = cy = 0.0
        tokens = re.findall(r"[MmLlHhVvCcSsQqTtAaZz]|-?\d*\.?\d+", d)
        i, cmd = 0, None
        while i < len(tokens):
            t = tokens[i]
            if re.match(r"[A-Za-z]", t):
                cmd = t
                i += 1
                continue
            n = lambda k: float(tokens[i + k])
            if cmd in "Mm":
                x, y = n(0), n(1)
                cx, cy = (x, y) if cmd == "M" else (cx + x, cy + y)
                xs.append(cx)
                ys.append(cy)
                i += 2
            elif cmd in "Ll":
                x, y = n(0), n(1)
                cx, cy = (x, y) if cmd == "L" else (cx + x, cy + y)
                xs.append(cx)
                ys.append(cy)
                i += 2
            elif cmd in "Hh":
                x = n(0)
                cx = x if cmd == "H" else cx + x
                xs.append(cx)
                ys.append(cy)
                i += 1
            elif cmd in "Vv":
                y = n(0)
                cy = y if cmd == "V" else cy + y
                xs.append(cx)
                ys.append(cy)
                i += 1
            elif cmd in "Cc":
                pts = [n(k) for k in range(6)]
                if cmd == "c":
                    pts = [pts[0] + cx, pts[1] + cy, pts[2] + cx, pts[3] + cy,
                           pts[4] + cx, pts[5] + cy]
                xs += pts[0::2]
                ys += pts[1::2]
                cx, cy = pts[4], pts[5]
                i += 6
            elif cmd in ("S", "s", "Q", "q"):
                pts = [n(k) for k in range(4)]
                if cmd.islower():
                    pts = [pts[0] + cx, pts[1] + cy, pts[2] + cx, pts[3] + cy]
                xs += pts[0::2]
                ys += pts[1::2]
                cx, cy = pts[2], pts[3]
                i += 4
            elif cmd in "Tt":
                x, y = n(0), n(1)
                cx, cy = (x, y) if cmd == "T" else (cx + x, cy + y)
                xs.append(cx)
                ys.append(cy)
                i += 2
            else:
                i += 1
    return [min(xs), min(ys), max(xs), max(ys)] if xs else None


def transform_d(d, s, tx, ty):
    """パスを s 倍して (tx,ty) 平行移動する。
    相対コマンドは倍率だけ、絶対コマンドは倍率と移動の両方を掛ける"""
    out = []
    tokens = re.findall(r"[MmLlHhVvCcSsQqTtAaZz]|-?\d*\.?\d+", d)
    i, cmd = 0, None
    nums = []

    def flush():
        if nums:
            out.append(",".join(fmt(v) for v in nums))
            del nums[:]

    while i < len(tokens):
        t = tokens[i]
        if re.match(r"[A-Za-z]", t):
            flush()
            cmd = t
            out.append(t)
            i += 1
            continue
        absolute = cmd.isupper()
        if cmd in "Hh":
            v = float(t) * s + (tx if absolute else 0)
            nums.append(v)
            i += 1
        elif cmd in "Vv":
            v = float(t) * s + (ty if absolute else 0)
            nums.append(v)
            i += 1
        else:
            x = float(tokens[i]) * s + (tx if absolute else 0)
            y = float(tokens[i + 1]) * s + (ty if absolute else 0)
            nums += [x, y]
            i += 2
    flush()
    return "".join(out)


DIGITS = 2


def fmt(v):
    """座標を短く。末尾のゼロは落とす"""
    s = ("%." + str(DIGITS) + "f") % v
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s if s not in ("", "-") else "0"


def round_d(d, digits=2):
    """d の数値を丸めて詰める（ファイルサイズ対策）。
    109 の座標系なので小数第1位でも見た目の差は出ない"""
    global DIGITS
    DIGITS = digits
    try:
        return transform_d(d, 1.0, 0.0, 0.0)
    finally:
        DIGITS = 2


# ───────────────────────── 分解 ─────────────────────────


def elem_kids(node):
    """直下の部品グループ。kvg_element を持たない位置グループは透過して降りる"""
    out = []
    for c in node:
        if c.tag != SVG + "g":
            continue
        if c.get("kvg_element"):
            out.append(c)
        else:
            out.extend(elem_kids(c))
    return out


# 浮いた画のうち、横・縦・払い・点は棚にある 一 丨 丿 丶 と同じものとして扱う。
# それ以外は筆画の名前（㇏ ㇕ ㇉ …）をそのまま部品名にする
STROKE_ALIAS = {"㇐": "一", "㇑": "丨", "㇒": "丿", "㇔": "丶"}

# 1つの部品につき、浮いた画を何本まで拾うか。
# 0 なら観や楽が作れない。6 以上だと鬱が13部品の筆画の山になる
MAX_ORPHANS = 3


def orphan_name(p):
    """浮いた画の名前。添え字つきの変種（㇑a など）は別物として扱う。
    まっすぐな 丨 と、五の2画目のような斜めに払う縦画は形が違いすぎて、
    同じ部品にすると均等拡縮では重ならない"""
    t = (p.get("kvg_type") or "").split("/")[0].strip()
    return STROKE_ALIAS.get(t, t or "㇐")


def paths_of_all(nodes):
    return [d for n in nodes for d in paths_of(n)]


def split(node):
    """node を部品に割る。[(名前, [ノード])] を返す。割れないなら None。

    2つのことをしている。

    1. KanjiVG には、どの部品グループにも属さない画がしばしば混ざっている。
       これを捨てると字が欠けるが、混ざっていることを理由に分解を諦めると、
       観（横画1本が浮いている）のような日常的な字がまるごと作れなくなる。
       そこで浮いた画は、その画自体を1つの部品として数える。

    2. 離れた位置に分かれて書かれる部品には kvg:part が振ってある。
       五の 二 は1画目と4画目に分かれていて、まとめないと
       「一本の横画」が 二 という名前の部品になってしまう"""
    kids = elem_kids(node)
    if len(kids) < 2:
        return None
    covered = {id(p) for k in kids for p in k.iter(SVG + "path")}
    orphans = [p for p in node.iter(SVG + "path") if id(p) not in covered]
    # 浮いた画が多いのは「1本はみ出した」ではなく
    # KanjiVG がそこを分析していないということ。割ると筆画の寄せ集めになる。
    # 鬯 は10画中6画が浮いていて、割ると鬱が13部品になってしまう
    if len(orphans) > MAX_ORPHANS:
        return None

    out, merging = [], {}
    for k in kids:
        el = k.get("kvg_element")
        if k.get("kvg_part") and el in merging:
            merging[el].append(k)
            continue
        group = [k]
        if k.get("kvg_part"):
            merging[el] = group
        out.append((el, group))
    out += [(orphan_name(p), [p]) for p in orphans]
    if len(out) < 2:
        return None

    # 書き順どおりに並べ直す
    pos = {id(p): i for i, p in enumerate(node.iter(SVG + "path"))}
    out.sort(key=lambda t: min(pos[id(p)] for n in t[1] for p in n.iter(SVG + "path")))
    return out


def decompose(nodes, name, min_strokes, max_depth, stop_at=frozenset(), depth=0):
    """[(部品名, [ノード])] を返す。これ以上割らない条件は下の5つ。

    stop_at（常用漢字）に当たったらそこで止めるのが肝。
    最後まで割ると 森＝木木木 になってしまい、
    「組み上げた字が次の部品になる」という遊びの背骨が消える。
    ここで止めれば 森＝木＋林 になり、林を作らないと森が作れなくなる"""
    if depth > 0 and name in stop_at:
        return [(name, nodes)]
    if len(paths_of_all(nodes)) <= min_strokes or depth >= max_depth:
        return [(name, nodes)]
    if len(nodes) != 1:
        return [(name, nodes)]        # kvg:part で離れている部品は割らない
    kids = split(nodes[0])
    if not kids:
        return [(name, nodes)]
    out = []
    for n, ks in kids:
        out += decompose(ks, n, min_strokes, max_depth, stop_at, depth + 1)
    return out


# ───────────────────────── 検算 ─────────────────────────

EXPECT = {
    "口": (3, [22.2, 29.5, 87.1, 83.0]),
    "力": (2, [13.4, 13.7, 89.2, 97.8]),
    "木": (4, [15.8, 10.5, 93.8, 98.5]),
    "日": (4, [31.5, 22.5, 79.2, 89.5]),
    "月": (4, [24.8, 13.5, 75.0, 101.2]),
}


def verify():
    print("── 外接矩形の検算（仕様書 3-2）──")
    ok = True
    for ch, (n_exp, b_exp) in EXPECT.items():
        node = stroke_root(load(ch))
        ds = paths_of(node)
        b = bbox(ds)
        hit = len(ds) == n_exp and all(abs(b[i] - b_exp[i]) < 0.11 for i in range(4))
        ok &= hit
        print("  %s %d画 [%s]  期待 [%s]  %s" % (
            ch, len(ds), ", ".join("%.2f" % v for v in b),
            ", ".join("%.1f" % v for v in b_exp), "一致" if hit else "★不一致★"))
    print("→", "パーサは正常" if ok else "★パーサが壊れている★")
    return ok


# ───────────────────────── 本体 ─────────────────────────


def read_joyo():
    p = os.path.join(ROOT, "data", "joyo.tsv")
    out = {}
    order = []
    for line in open(p, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line:
            continue
        f = line.split("\t")
        out[f[0]] = f[1] if len(f) > 1 else ""
        order.append(f[0])
    return order, out


def build(min_strokes, max_depth=8):
    """常用漢字を分解して (kanji, part_occurrences, failures) を返す"""
    order, yomi = read_joyo()
    joyo = frozenset(order)
    kanji = {}
    failures = []
    occ = defaultdict(list)   # 部品名 -> [(面積, d のリスト, box)]

    for ch in order:
        node = stroke_root(load(ch))
        if node is None:
            failures.append(ch)
            continue
        leaves = decompose([node], ch, min_strokes, max_depth, joyo)
        parts, layout, pos = [], [], []
        broken = False
        for name, nds in leaves:
            ds = paths_of_all(nds)
            b = bbox(ds)
            if b is None:
                broken = True
                break
            parts.append(name)
            layout.append(b)
            pos.append(nds[0].get("kvg_position") or "")
            area = (b[2] - b[0]) * (b[3] - b[1])
            occ[name].append((area, ds, b))
        if broken:
            failures.append(ch)
            continue
        kanji[ch] = {
            "parts": parts,
            "layout": layout,
            "pos": pos,
            "d": paths_of(node),
            "yomi": yomi.get(ch, ""),
        }
    return kanji, occ, failures


def part_shapes(occ):
    """部品の単体図形を決める。
    自前の SVG があればそれを使い、無ければ一番大きく描かれている実例を採る"""
    parts = {}
    from_file, from_situ = 0, 0
    for name, lst in occ.items():
        node = stroke_root(load(name)) if len(name) == 1 else None
        if node is not None:
            ds = paths_of(node)
            b = bbox(ds)
            if b is not None:
                parts[name] = {"d": ds, "box": b, "src": "file"}
                from_file += 1
                continue
        # 自前の SVG が無い部品は、一番大きく描かれている実例を採る。
        # 大きさは変えずに中央へ寄せるだけ（拡大すると棚の中で不釣り合いに大きくなる）
        area, ds, b = max(lst, key=lambda t: t[0])
        tx = 54.5 - (b[0] + b[2]) / 2
        ty = 54.5 - (b[1] + b[3]) / 2
        nds = [transform_d(d, 1.0, tx, ty) for d in ds]
        parts[name] = {"d": nds, "box": bbox(nds), "src": "situ"}
        from_situ += 1
    return parts, from_file, from_situ


def survey():
    print("── 粒度の比較（仕様書 11-2）──")
    print("  min_strokes  部品の種類  1字あたりの部品数  1部品だけの字")
    for ms in (2, 3, 4):
        kanji, occ, fails = build(ms)
        counts = [len(v["parts"]) for v in kanji.values()]
        atoms = sum(1 for v in kanji.values() if len(v["parts"]) == 1)
        print("  %11d  %10d  %17.2f  %12d" % (
            ms, len(occ), sum(counts) / len(counts), atoms))


def uniqueness(kanji):
    """部品の集合だけで字が決まるか"""
    key = lambda v: "".join(sorted(v["parts"]))
    groups = defaultdict(list)
    for ch, v in kanji.items():
        groups[key(v)].append(ch)
    uniq = sum(1 for g in groups.values() if len(g) == 1)
    clashes = sorted((g for g in groups.values() if len(g) > 1), key=len, reverse=True)
    return uniq, clashes


def reachable(kanji, start):
    """開始部品から作れる字を全部作り、材料に加え、を繰り返す"""
    have = set(start)
    found = set()
    key = lambda v: tuple(sorted(v["parts"]))
    recipes = [(ch, key(v)) for ch, v in kanji.items()]
    while True:
        added = False
        for ch, need in recipes:
            if ch in found or ch in have:
                continue
            if all(p in have for p in need) and not (len(need) == 1 and need[0] == ch):
                found.add(ch)
                have.add(ch)
                added = True
        if not added:
            break
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--survey", action="store_true")
    ap.add_argument("--min-strokes", type=int, default=2)
    ap.add_argument("--out")
    a = ap.parse_args()

    if a.verify:
        sys.exit(0 if verify() else 1)
    if a.survey:
        survey()
        return

    ms = a.min_strokes
    print("── 抽出（min_strokes=%d）──" % ms)
    kanji, occ, fails = build(ms)
    parts, n_file, n_situ = part_shapes(occ)

    print("  分解できた常用漢字   %d / 2136" % len(kanji))
    if fails:
        print("  できなかった字       %s" % " ".join(fails))
    print("  部品の種類           %d（自前SVG %d / 実例から %d）" % (len(parts), n_file, n_situ))

    dist = Counter(len(v["parts"]) for v in kanji.values())
    print("  1字あたりの部品数     " + " / ".join(
        "%d個:%d字" % (k, dist[k]) for k in sorted(dist)))

    freq = Counter()
    for v in kanji.values():
        freq.update(v["parts"])
    print("  よく使う部品 上位30")
    print("    " + "  ".join("%s(%d)" % (p, n) for p, n in freq.most_common(30)))

    uniq, clashes = uniqueness(kanji)
    print("  部品の集合だけで決まる字  %d / %d" % (uniq, len(kanji)))
    print("  ぶつかる組               %d組" % len(clashes))
    for g in clashes[:40]:
        print("    " + "/".join(g))
    if len(clashes) > 40:
        print("    ...ほか %d組" % (len(clashes) - 40))

    # 材料として使われる字（＝棚に残す価値のある字）
    used = set()
    for v in kanji.values():
        used.update(v["parts"])
    ingredients = sorted(used & set(kanji))
    print("  他の字の材料になる常用漢字  %d字" % len(ingredients))

    # 自分自身にしか分解できない字＝これ以上作れない原子
    atoms = sorted(ch for ch, v in kanji.items() if v["parts"] == [ch])
    print("  作れない字（原子）          %d字" % len(atoms))

    # 素の部品（漢字として作れないもの）。よく使う順に並べ、仕様書の開始10個を先頭に置く
    base_set = set(p for p in parts if p not in kanji or p in atoms)
    head = [p for p in "一丨丶丿十口木日月力" if p in base_set]
    base = head + [p for p, _ in freq.most_common() if p in base_set and p not in head]
    base += sorted(p for p in base_set if p not in set(base))
    print("  素の部品（作れないもの）    %d種" % len(base))

    if not a.out:
        return

    # ── 書き出し ──
    out = {
        "meta": {
            "source": "KanjiVG",
            "license": "CC BY-SA 3.0",
            "url": "http://kanjivg.tagaini.net",
            "minStrokes": ms,
            "partCount": len(parts),
            "kanjiCount": len(kanji),
            "buildable": len(kanji) - len(atoms),
        },
        "parts": {},
        "kanji": {},
        "base": base,          # 素の部品。よく使う順＝解放していく順
        "atoms": atoms,        # 部品そのものである常用漢字（組み立てられない）
        "ingredients": ingredients,
    }
    for name, p in parts.items():
        out["parts"][name] = {
            "d": [round_d(d) for d in p["d"]],
            "box": [round(v, 2) for v in p["box"]],
            "strokes": len(p["d"]),
        }
    strokes = {}
    for ch, v in kanji.items():
        out["kanji"][ch] = {
            "parts": v["parts"],
            "layout": [[round(x, 1) for x in b] for b in v["layout"]],
            "pos": v["pos"],
            "yomi": v["yomi"],
        }
        # 正解の重ね表示は別ファイル。無くても遊べるので後から読む
        strokes[ch] = [round_d(d, 1) for d in v["d"]]

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    sp = os.path.join(os.path.dirname(a.out), "strokes.json")
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(strokes, f, ensure_ascii=False, separators=(",", ":"))
    print("  書き出し  %s  %.2f MB" % (a.out, os.path.getsize(a.out) / 1e6))
    print("  書き出し  %s  %.2f MB" % (sp, os.path.getsize(sp) / 1e6))


if __name__ == "__main__":
    main()
