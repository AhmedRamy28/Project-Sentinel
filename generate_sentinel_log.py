#!/usr/bin/env python3
"""
generate_sentinel_log.py — Project Sentinel synthetic log generator.

Builds a deliberately messy data/raw/ground_station_log.csv FROM a real list
of NEO ids (pulled live by the student from the NASA NeoWs API), instead of
shipping a static pre-made file. Because the log is generated from whatever
ids the student actually pulled, a real join will always have real matches —
but three flaws are injected on every run so a naive 1:1 join still fails:

    1. Dropped ids  (~10% of the input ids are simply missing from the log,
                      simulating sensor downtime)
    2. Ghost ids    (~10% extra, fabricated ids appear in the log that were
                      never in the input, simulating unrelated network noise)
    3. Dirty values (observatory_code's own choice list includes a whitespace-
                      padded code and an "UNKNOWN" placeholder; confidence_score
                      occasionally comes back blank, whitespace-padded, "N/A",
                      or "null")

Usage (terminal):
    python generate_sentinel_log.py --input-ids extracted_ids.txt
    python generate_sentinel_log.py --input-ids extracted_ids.txt --output data/raw/ground_station_log.csv --seed 7
    python generate_sentinel_log.py                       # no file yet -> runs a built-in smoke test

Usage (notebook / direct import):
    from generate_sentinel_log import generate_sentinel_log
    generate_sentinel_log(my_neo_id_list)
"""

import argparse
import csv
import random
from pathlib import Path

DEFAULT_OUTPUT = Path("data/raw/ground_station_log.csv")
FIELDNAMES = ["neo_id", "observatory_code", "confidence_score"]

OBSERVATORY_CODES = ["G96", "703", "I41", "F51", "W88", " G96", "UNKNOWN"]

DROP_RATE = 0.10
GHOST_RATE = 0.10
DIRTY_RATE = 0.15

# Real, plausible NEO reference ids so the script produces a genuine-looking
# file even with zero setup.
FALLBACK_IDS = [
    "3542519", "2000433", "3840869", "54016849", "3671553",
    "2523775", "3792442", "2467291", "3268660", "2099942",
]


def _dirty_confidence_score():
    """Mostly a clean 2-decimal float string; occasionally blank, padded, 'N/A', or 'null'."""
    clean = f"{random.uniform(0.50, 0.99):.2f}"
    if random.random() < DIRTY_RATE:
        return random.choice(["", "N/A", "null", f"{clean} "])
    return clean


def _fabricate_ghost_id(used_ids):
    """Build a plausible NEO-id-shaped string that is not already in use."""
    while True:
        candidate = str(random.randint(1_000_000, 4_999_999))
        if candidate not in used_ids:
            return candidate


def generate_sentinel_log(id_list, output_path=None, seed=None):
    """
    Write a messy ground_station_log.csv built from a real list of NEO ids.

    Args:
        id_list: iterable of NEO id strings (the API's `id` / `neo_reference_id`).
        output_path: where to write the CSV. Defaults to data/raw/ground_station_log.csv;
            parent folders are created automatically if they don't exist.
        seed: optional int for reproducible output (useful for grading/debugging).
            Leave as None for a fresh random log on every run.

    Returns:
        pathlib.Path to the file that was written.
    """
    if seed is not None:
        random.seed(seed)

    output_path = Path(output_path) if output_path else DEFAULT_OUTPUT
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ids = [str(i).strip() for i in id_list if str(i).strip()]

    n_drop = round(len(ids) * DROP_RATE)
    dropped = set(random.sample(ids, n_drop)) if n_drop else set()
    surviving_ids = [i for i in ids if i not in dropped]

    n_ghost = round(len(ids) * GHOST_RATE)
    used_ids = set(ids)
    ghost_ids = []
    for _ in range(n_ghost):
        ghost = _fabricate_ghost_id(used_ids)
        used_ids.add(ghost)
        ghost_ids.append(ghost)

    all_ids = surviving_ids + ghost_ids
    random.shuffle(all_ids)

    rows = [
        {
            "neo_id": neo_id,
            "observatory_code": random.choice(OBSERVATORY_CODES),
            "confidence_score": _dirty_confidence_score(),
        }
        for neo_id in all_ids
    ]

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"[generate_sentinel_log] {len(ids)} input ids -> {len(rows)} log rows "
        f"({len(dropped)} dropped, {len(ghost_ids)} ghost ids injected) -> {output_path}"
    )
    return output_path


def _load_ids_from_file(path):
    """Read one id per line from a plain text file, ignoring blank lines."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"Could not find {p}. Pass a text file with one NEO id per line via "
            "--input-ids, or omit --input-ids to run the built-in smoke test."
        )
    return [line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _cli():
    parser = argparse.ArgumentParser(
        description="Generate a messy data/raw/ground_station_log.csv for Project Sentinel."
    )
    parser.add_argument(
        "--input-ids", default=None,
        help="Path to a text file with one NEO id per line. Omit to run a built-in smoke test.",
    )
    parser.add_argument(
        "--output", default=str(DEFAULT_OUTPUT),
        help=f"Output CSV path (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="Optional random seed for reproducible output.",
    )
    args = parser.parse_args()

    if args.input_ids:
        ids = _load_ids_from_file(args.input_ids)
    else:
        print("No --input-ids given; running with the built-in fallback id list as a smoke test.")
        ids = FALLBACK_IDS

    generate_sentinel_log(ids, output_path=args.output, seed=args.seed)


if __name__ == "__main__":
    _cli()
