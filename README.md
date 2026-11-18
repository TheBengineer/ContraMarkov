# ContraMarkov

A Markov chain of contra dance moves, built from move trigrams across a set of dances, and a single-page viewer for browsing it as a force-directed graph.

**[Open the live viewer](https://thebengineer.github.io/ContraMarkov/contra_markov.html)**, or download [`contra_markov.html`](contra_markov.html) and open it in a browser. The chain data is embedded in the page, so it works offline.

## What's in the chain

[`contra_markov.json`](contra_markov.json) has one chain per level of detail: `coarse`, `mid` and `fine`. Finer levels tell apart variants like `allemande left|men|1 & 1/2`.

| Key | Meaning |
| --- | --- |
| `first_order[move]` | Distribution of the next move given the current one |
| `second_order["a >> b"]` | Distribution of the next move given the last two |
| `nodes[].beats` | How long the move lasts: `typical`, every length seen (`options`), `range`, `adjustable`, component `parts` (balance 4 + swing 12) and `source` |
| `nodes[].phrase_starts` | Which beat (1–16) of a phrase the move usually starts on |
| `nodes[].in_data` | `false` for standard figures added so they can be sequenced by hand |

Every transition has a raw `count`, a popularity-weighted `pop`, a probability under each weighting (`p`, `p_pop`), and the dances it comes from.

**Beats.** The source data only records where each move starts within a 16-beat phrase. Move lengths are measured from the gap to the next move's start in each dance (`observed`). Balance-and-swing is never the first move of a trigram, so its length comes from the gap between its neighbours (`inferred`). Moves with no timing data use the usual contra length (`default`). The source doesn't say which phrase (A or B) a move falls in, only the beat within the phrase.

## The viewer

- **Browse:** click a move to start a path, then click a likely next move in the graph or side panel to keep going. Next moves are ranked from the last two moves (2nd order) or the last move only (1st order), by raw count or popularity.
- **Dance card:** the path is laid out in A1 / A2 / B1 / B2 with the start beat and length of each move, plus a 64-beat bar. Moves with a range of lengths stretch to the end of the phrase, or shrink so a fixed-length next move ends on it. Click a beat badge to change a move's length by hand.
- **♪ on phrase** marks next moves that usually start on the beat where they'd land.
- **Off-chain moves:** add any legal move from the *Any move* list, or Shift-click a node in the graph, even if the chain has never seen it there. These steps get a dashed outline.
- **Random walk** generates a dance that fills exactly 64 beats and doesn't loop back to its first move.
- **Undo / redo** with Ctrl+Z and Ctrl+Y.
- **Graph:** drag a node to pin it, click it to unpin. Scroll to zoom. Hovering a move in the panel highlights its edge.
- The level and path are kept in the URL, so you can bookmark or share a path.

## Rebuilding

Both output files are generated from a `trigram_counts.csv` of move trigrams:

```bash
python build_chain.py path/to/trigram_counts.csv
```

This writes `contra_markov.json`, and `contra_markov.html` with the chain embedded into [`viewer_template.html`](viewer_template.html). To change the viewer, edit the template, not the generated HTML. Conventional beat counts and the extra standard figures live in `DEFAULT_BEATS` and `EXTRA_MOVES` in [`build_chain.py`](build_chain.py).
