"""Batch screen: run the analyser across the peer universe to surface high-scoring names.

This module only ORCHESTRATES what already exists. It calls analyse() and
reverse_dcf() unchanged, sums the checklist scores they already produce, and
ranks the results. No thresholds and no calculations are introduced here — the
one derived number, `total_score`, is just the sum of each framework's existing
score/total fraction.

Universe: every ticker in the peers.SECTOR_PEERS lists, minus the two
out-of-scope sectors (Financial Services, Real Estate) — deduped, order
preserved. The peer cache (peer_cache.json) is reused automatically by
peer_analysis(), so the peers of each sector are fetched once and then hit.

CLI:
    python screen.py            # screen the whole universe
    python screen.py 10         # smoke-test: first 10 tickers only

Prints a progress line per ticker as it runs, then a ranked table, and writes
screen_results.csv.
"""

import csv
import os
import sys
import time

from analyse import analyse, OUT_OF_SCOPE_SECTORS
from peers import SECTOR_PEERS
from reverse_dcf import reverse_dcf

# Polite rate limiting between yfinance calls. yfinance has no official rate
# limit; these gaps keep the batch from hammering it. Tune down if you trust it.
SLEEP_BETWEEN_TICKERS = 1.5   # seconds, after each ticker
SLEEP_BETWEEN_CALLS = 0.5     # seconds, between analyse() and reverse_dcf()

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screen_results.csv")

# The seven frameworks in analyse.py order, with short column codes for the table.
FRAMEWORKS = [
    ("Buffett quality", "Buf"),
    ("Lynch GARP", "Lyn"),
    ("Graham value", "Gra"),
    ("Goldberg technical", "Gol"),
    ("Bajaj compounder", "Baj"),
    ("Greenblatt magic", "Grn"),
    ("Inglis-Jones / Gleave", "IJG"),
]


def build_universe():
    """All tickers in the peer lists, minus out-of-scope sectors, deduped."""
    seen = set()
    universe = []
    for sector, tickers in SECTOR_PEERS.items():
        if sector in OUT_OF_SCOPE_SECTORS:
            continue
        for t in tickers:
            if t not in seen:
                seen.add(t)
                universe.append(t)
    return universe


def screen_one(ticker):
    """Run both analyses for one ticker and reduce them to a flat result row.

    Never raises: analyse() and reverse_dcf() are each wrapped so that a failure
    in one still records whatever the other produced.
    """
    row = {
        "ticker": ticker,
        "sector": None,
        "total_score": 0.0,
        "n_frameworks": 0,
        "framework_scores": {name: None for name, _ in FRAMEWORKS},
        "reconciled": None,      # True / False / None(=error or out of scope)
        "implied_growth": None,
        "hist_rev_cagr": None,
        "flags": [],
        "notes": [],
        "errors": [],
    }

    # --- analyse(): the seven checklists ---
    try:
        a = analyse(ticker)
        if a.get("out_of_scope"):
            row["sector"] = a.get("sector")
            row["notes"].append("analyse: out of scope sector")
        else:
            row["sector"] = a.get("sector")
            checklists = a.get("checklists", {})
            total = 0.0
            present = 0
            for name, _code in FRAMEWORKS:
                c = checklists.get(name)
                if c and c.get("total"):
                    frac = c["score"] / c["total"]
                    total += frac
                    present += 1
                    row["framework_scores"][name] = (c["score"], c["total"])
            row["total_score"] = total
            row["n_frameworks"] = present
            row["notes"].extend(a.get("notes", []))
    except Exception as exc:
        row["errors"].append(f"analyse: {exc.__class__.__name__}: {exc}")

    time.sleep(SLEEP_BETWEEN_CALLS)

    # --- reverse_dcf(): reconciliation + plausibility flags ---
    try:
        r = reverse_dcf(ticker)
        if r.get("out_of_scope"):
            row["notes"].append("reverse_dcf: out of scope sector")
        elif r.get("error"):
            row["flags"].append(f"DCF error: {r['error']}")
        else:
            row["reconciled"] = bool(r.get("reconciled"))
            row["implied_growth"] = r.get("implied_growth")
            row["hist_rev_cagr"] = r.get("hist_rev_cagr")
            row["flags"].extend(r.get("flags", []))
    except Exception as exc:
        row["errors"].append(f"reverse_dcf: {exc.__class__.__name__}: {exc}")

    return row


def _rec_cell(row):
    if row["errors"] and row["reconciled"] is None:
        return "ERR"
    if row["reconciled"] is True:
        return "Y"
    if row["reconciled"] is False:
        return "N"
    return "-"


def _fw_cell(pair):
    return f"{pair[0]}/{pair[1]}" if pair else "-"


def print_table(rows):
    """Ranked table, highest total_score first."""
    ranked = sorted(rows, key=lambda r: (-r["total_score"], r["ticker"]))

    codes = [code for _, code in FRAMEWORKS]
    header = (
        f"{'#':>3}  {'Ticker':<6} {'Total':>6}  "
        + " ".join(f"{c:>4}" for c in codes)
        + f"  {'Rec':>3} {'Flags':>5}"
    )
    print()
    print("Framework codes: " + ", ".join(f"{c}={name}" for name, c in FRAMEWORKS))
    print("Total = sum of score/total across the frameworks present (max 7.00).")
    print()
    print(header)
    print("-" * len(header))
    for i, row in enumerate(ranked, start=1):
        fw = " ".join(f"{_fw_cell(row['framework_scores'][name]):>4}" for name, _ in FRAMEWORKS)
        print(
            f"{i:>3}  {row['ticker']:<6} {row['total_score']:>6.2f}  "
            f"{fw}  {_rec_cell(row):>3} {len(row['flags']):>5}"
        )
    return ranked


def write_csv(rows, path=CSV_PATH):
    fieldnames = (
        ["rank", "ticker", "sector", "total_score", "n_frameworks"]
        + [name for name, _ in FRAMEWORKS]
        + ["reconciled", "implied_growth", "hist_rev_cagr", "n_flags", "flags", "notes", "errors"]
    )
    ranked = sorted(rows, key=lambda r: (-r["total_score"], r["ticker"]))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for i, row in enumerate(ranked, start=1):
            record = {
                "rank": i,
                "ticker": row["ticker"],
                "sector": row["sector"] or "",
                "total_score": f"{row['total_score']:.4f}",
                "n_frameworks": row["n_frameworks"],
                "reconciled": _rec_cell(row),
                "implied_growth": "" if row["implied_growth"] is None else row["implied_growth"],
                "hist_rev_cagr": "" if row["hist_rev_cagr"] is None else f"{row['hist_rev_cagr']:.4f}",
                "n_flags": len(row["flags"]),
                "flags": " | ".join(row["flags"]),
                "notes": " | ".join(row["notes"]),
                "errors": " | ".join(row["errors"]),
            }
            for name, _ in FRAMEWORKS:
                record[name] = _fw_cell(row["framework_scores"][name])
            w.writerow(record)
    return path


def run(limit=None):
    universe = build_universe()
    if limit is not None:
        universe = universe[:limit]
    n = len(universe)
    print(f"Screening {n} tickers (peer universe minus {', '.join(OUT_OF_SCOPE_SECTORS)}).")
    print(f"Rate limiting: {SLEEP_BETWEEN_CALLS}s between calls, "
          f"{SLEEP_BETWEEN_TICKERS}s between tickers.\n")

    rows = []
    start = time.time()
    for idx, ticker in enumerate(universe, start=1):
        try:
            row = screen_one(ticker)
        except Exception as exc:  # defensive: screen_one already guards, but never abort the run
            row = {
                "ticker": ticker, "sector": None, "total_score": 0.0, "n_frameworks": 0,
                "framework_scores": {name: None for name, _ in FRAMEWORKS},
                "reconciled": None, "implied_growth": None, "hist_rev_cagr": None,
                "flags": [], "notes": [], "errors": [f"{exc.__class__.__name__}: {exc}"],
            }
        rows.append(row)

        # Progress line, so the run can be watched.
        status = "ERR" if row["errors"] else "ok "
        print(
            f"[{idx:>3}/{n}] {row['ticker']:<6} {status} "
            f"score={row['total_score']:5.2f}/7 ({row['n_frameworks']}/7 fw)  "
            f"rec={_rec_cell(row):<3} flags={len(row['flags'])}"
            + (f"  {row['errors'][0]}" if row["errors"] else "")
        )

        if idx < n:
            time.sleep(SLEEP_BETWEEN_TICKERS)

    elapsed = time.time() - start
    ranked = print_table(rows)
    path = write_csv(rows)
    n_err = sum(1 for r in rows if r["errors"])
    print()
    print(f"Done: {n} tickers in {elapsed:.0f}s, {n_err} with errors. Wrote {path}")
    return ranked


if __name__ == "__main__":
    lim = None
    if len(sys.argv) > 1:
        try:
            lim = int(sys.argv[1])
        except ValueError:
            print(f"Usage: python screen.py [limit]   (got {sys.argv[1]!r})")
            sys.exit(1)
    run(limit=lim)
