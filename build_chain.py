"""Build a contra dance move Markov chain (JSON) from trigram_counts.csv.

Usage: python build_chain.py <trigram_counts.csv> [out_dir]

Writes:
  contra_markov.json   - the chain (first- and second-order, per level)
  contra_markov.html   - viewer with the chain embedded (from viewer_template.html)
"""
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
PHRASE = 16  # first_move_beat_offsets are positions within a 16-beat phrase

# Conventional beat counts, used only for moves the offsets can't measure.
DEFAULT_BEATS = {
    "swing": [8, 10, 12], "allemande left": [8, 6, 4], "allemande right": [8, 6, 4],
    "do-si-do": [8, 6], "ladies chain": [8], "star left": [8], "star right": [8],
    "circle left": [8, 6], "circle right": [8, 6], "hey": [16, 8], "ricochet hey": [8],
    "square through": [8, 16], "turn contra corners": [16], "circulate": [4, 8],
    "cross trail through": [4], "grand right and left": [8, 4], "long lines forward and back": [8],
    "petronella turn": [4], "balance ring": [4], "California twirl": [4], "pass through": [2],
}


def parse_offsets(s):
    return sorted({int(o) for o in s.split(",") if o.strip() != ""})


def default_beats(move):
    parts = move.split("|")
    base = parts[0]
    if "balance" in parts[1:] and base == "swing":
        return [16, 12]
    if base == "hey" and "1/2" in parts:
        return [8]
    if base == "hey" and "3/4" in parts:
        return [12]
    for key in (base, base.split(" ")[0]):
        if key in DEFAULT_BEATS:
            return DEFAULT_BEATS[key]
    return [8]


def beat_parts(move, total):
    """Split compound moves into their component figures."""
    parts = move.split("|")
    if parts[0] == "swing" and "balance" in parts[1:] and total > 4:
        return [{"name": "balance", "beats": 4}, {"name": "swing", "beats": total - 4}]
    return [{"name": parts[0], "beats": total}]


def measure_beats(lrows):
    """Recover how many beats each move lasts from where consecutive moves start.

    Rebuild each dance's trigrams, and wherever move_1's start offset is known
    for both a trigram (a,b,c) and its follower (b,c,·), a lasts the gap between
    them. Moves that never appear as move_1 (balance-and-swing) are inferred from
    the span between the move before them and the move after, minus the typical
    length of the move before.
    """
    per_dance = defaultdict(list)
    for r in lrows:
        offs = parse_offsets(r["first_move_beat_offsets"])
        off = offs[0] if len(offs) == 1 else None
        for d in (d.strip() for d in r["dance_list"].split(";")):
            if d:
                per_dance[d].append((r["move_1"], r["move_2"], r["move_3"], off))

    node = defaultdict(Counter)
    starts = defaultdict(Counter)  # move -> beat within the 16-beat phrase it starts on
    edge = defaultdict(Counter)
    for tris in per_dance.values():
        for a, b, c, oa in tris:
            if oa is not None:
                starts[a][oa] += 1
            nxt = [t for t in tris if t[0] == b and t[1] == c]
            if oa is None or len(nxt) != 1 or nxt[0][3] is None:
                continue
            beats = (nxt[0][3] - oa) % PHRASE or PHRASE
            node[a][beats] += 1
            edge[(a, b)][beats] += 1

    typical = {m: c.most_common(1)[0][0] for m, c in node.items()}
    inferred = defaultdict(Counter)
    for tris in per_dance.values():
        for x, a, b, ox in tris:
            if a in node or ox is None or x not in typical:
                continue
            nb = [t for t in tris if t[0] == b]
            if len(nb) != 1 or nb[0][3] is None:
                continue
            beats = (nb[0][3] - ox - typical[x]) % PHRASE or PHRASE
            inferred[a][beats] += 1
            starts[a][(ox + typical[x]) % PHRASE] += 1
            edge[(a, b)][beats] += 1

    def summary(counter, source):
        total = sum(counter.values())
        opts = [(b, n) for b, n in counter.most_common()
                # inference stacks two estimates, so drop one-off outliers
                if source != "inferred" or n >= 2 or n / total >= 0.25]
        return {
            "typical": opts[0][0],
            "options": [{"beats": b, "n": n} for b, n in sorted(opts)],
            "source": source,
        }

    out = {m: summary(c, "observed") for m, c in node.items()}
    out.update({m: summary(c, "inferred") for m, c in inferred.items()})
    edges = {k: summary(c, "observed") for k, c in edge.items()}
    phrase = {m: [{"beat": o + 1, "n": n} for o, n in sorted(c.items())] for m, c in starts.items()}
    return out, edges, phrase


def node_beats(move, measured):
    b = measured.get(move) or {
        "typical": default_beats(move)[0],
        "options": [{"beats": x, "n": 0} for x in sorted(default_beats(move))],
        "source": "default",
    }
    lengths = [o["beats"] for o in b["options"]]
    return {
        **b,
        # a move seen at several lengths can be stretched or shrunk anywhere in between
        "adjustable": len(lengths) > 1,
        "range": [min(lengths), max(lengths)],
        "parts": beat_parts(move, b["typical"]),
    }


def build(rows):
    levels = {}
    by_level = defaultdict(list)
    for r in rows:
        by_level[r["level"]].append(r)

    for level, lrows in by_level.items():
        stat = lambda: {"count": 0, "pop": 0, "dances": set()}
        head = defaultdict(lambda: defaultdict(stat))
        tail = defaultdict(lambda: defaultdict(stat))
        second = defaultdict(lambda: defaultdict(stat))

        for r in lrows:
            m1, m2, m3 = r["move_1"], r["move_2"], r["move_3"]
            n = int(r["instances"])
            pop = int(r["pop_weighted"])
            dances = {d.strip() for d in r["dance_list"].split(";") if d.strip()}

            for target in (head[m1][m2], tail[m2][m3], second[(m1, m2)][m3]):
                target["count"] += n
                target["pop"] += pop
                target["dances"] |= dances

        # In a fully cyclic dataset every bigram is both the head and the tail of
        # one trigram, so the two sums agree. The CSV has gaps (sequence ends,
        # filtered rows), so take whichever side saw more of each bigram.
        first = defaultdict(dict)
        for a in set(head) | set(tail):
            for b in set(head.get(a, {})) | set(tail.get(a, {})):
                h, t = head.get(a, {}).get(b), tail.get(a, {}).get(b)
                best = max((x for x in (h, t) if x), key=lambda x: (x["count"], x["pop"]))
                first[a][b] = {**best, "dances": (h or stat())["dances"] | (t or stat())["dances"]}

        node_stats = defaultdict(stat)
        for a, d in first.items():
            for b, s in d.items():
                node_stats[a]["count"] += s["count"]
                node_stats[a]["pop"] += s["pop"]
                node_stats[a]["dances"] |= s["dances"]
        # moves that only ever appear last: size them by what flows in
        for a, d in first.items():
            for b, s in d.items():
                if b not in first:
                    node_stats[b]["count"] += s["count"]
                    node_stats[b]["pop"] += s["pop"]
                    node_stats[b]["dances"] |= s["dances"]

        measured, edge_beats, phrase_starts = measure_beats(lrows)

        def finish(dist, src=None):
            tot_c = sum(v["count"] for v in dist.values()) or 1
            tot_p = sum(v["pop"] for v in dist.values()) or 1
            out = [
                {
                    "to": k,
                    "count": v["count"],
                    "pop": v["pop"],
                    "p": round(v["count"] / tot_c, 4),
                    "p_pop": round(v["pop"] / tot_p, 4),
                    "dances": sorted(v["dances"]),
                    **({"from_beats": edge_beats[(src, k)]} if (src, k) in edge_beats else {}),
                }
                for k, v in dist.items()
            ]
            out.sort(key=lambda e: (-e["count"], -e["pop"], e["to"]))
            return out

        all_moves = set(node_stats) | {m for d in first.values() for m in d}
        nodes = []
        for m in sorted(all_moves, key=str.lower):
            s = node_stats.get(m, {"count": 0, "pop": 0, "dances": set()})
            nodes.append({
                "id": m,
                "base": m.split("|")[0],
                "count": s["count"],
                "pop": s["pop"],
                "n_dances": len(s["dances"]),
                "beats": node_beats(m, measured),
                "phrase_starts": phrase_starts.get(m, []),
            })

        levels[level] = {
            "nodes": nodes,
            "first_order": {a: finish(d, a) for a, d in first.items()},
            "second_order": {f"{a} >> {b}": finish(d) for (a, b), d in second.items()},
        }

    all_dances = sorted({d.strip() for r in rows for d in r["dance_list"].split(";") if d.strip()})
    return {
        "meta": {
            "description": "Markov chain of contra dance moves. first_order[move] gives "
                           "the next-move distribution; second_order['a >> b'] gives the "
                           "distribution of the move after a then b.",
            "weights": {
                "count": "raw instances",
                "pop": "pop_weighted (popularity-weighted instances)",
            },
            "beats": "nodes[].beats: how long the move lasts. typical = most common, "
                     "options = every length seen with how often (n), parts = component "
                     "figures (balance 4 + swing 12). source: observed (measured from "
                     "first_move_beat_offsets), inferred (from the span between neighbours), "
                     "or default (contra convention, no data). first_order edges carry "
                     "from_beats: the length of the source move when followed by that move. "
                     "adjustable moves (seen at more than one length) can take any length "
                     "in range; the viewer stretches them to the phrase end, or shrinks "
                     "them so a fixed-length next move ends on the phrase end.",
            "dance_beats": 64,
            "phrases": "The music is AABB: four 16-beat phrases A1, A2, B1, B2. "
                       "nodes[].phrase_starts: which beat (1-16) of a phrase the move "
                       "starts on, with how often. The source data gives position within "
                       "a phrase but not which phrase, so A vs B is not recorded.",
            "level_order": [l for l in ("coarse", "mid", "fine") if l in levels],
            "n_dances": len(all_dances),
        },
        "levels": levels,
    }


def main():
    src = Path(sys.argv[1])
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE
    with src.open(encoding="utf-8", newline="") as f:
        chain = build(list(csv.DictReader(f)))

    (out_dir / "contra_markov.json").write_text(json.dumps(chain, indent=1, ensure_ascii=False), encoding="utf-8")

    template = (HERE / "viewer_template.html").read_text(encoding="utf-8")
    embedded = json.dumps(chain, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    (out_dir / "contra_markov.html").write_text(template.replace("/*__CHAIN_DATA__*/null", embedded), encoding="utf-8")

    for lv, d in chain["levels"].items():
        print(f"{lv}: {len(d['nodes'])} moves, {len(d['first_order'])} first-order states, "
              f"{len(d['second_order'])} second-order states")


if __name__ == "__main__":
    main()
