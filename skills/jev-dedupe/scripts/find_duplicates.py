"""Find duplicate records with Jev and write a merge plan. The input file is not changed.

Step 1: Code finds candidate pairs cheaply (shared words, similar names).
Step 2: Jev answers one yes/no question per pair: "Same real-world entity?"
        Many pairs go in one request. Requests run in parallel.
Step 3: Pairs at or above the threshold are joined into merge groups.

  python find_duplicates.py companies.csv --fields name city --out plan.json
  python find_duplicates.py contacts.json --fields name email --id-field id --threshold 0.99
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "jev-setup" / "scripts"))
from jev_client import JevError, ask, noul  # noqa: E402

STOP_TOKENS = {"the", "and", "of", "inc", "llc", "ltd", "co", "corp", "corporation", "company", "group", "gmbh", "plc", "a", "an"}
WORD = re.compile(r"[a-z0-9]+")


def load_records(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".csv":
        return list(csv.DictReader(text.splitlines()))
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("A JSON input must be a list of objects.")
    return data


def tokens(record: dict, fields: list[str]) -> list[str]:
    words = []
    for field in fields:
        words.extend(WORD.findall(str(record.get(field, "")).lower()))
    return [w for w in words if w not in STOP_TOKENS]


def candidate_pairs(records: list[dict], fields: list[str], min_overlap: float, max_block: int, max_pairs: int) -> list[tuple[int, int, float]]:
    """Blocking: only compare records that share a word. Skip very common words."""
    token_sets = [set(tokens(r, fields)) for r in records]
    first_tokens = [(tokens(r, fields) or [""])[0] for r in records]
    index: dict[str, list[int]] = defaultdict(list)
    for i, words in enumerate(token_sets):
        for word in words:
            index[word].append(i)

    seen: dict[tuple[int, int], float] = {}
    for word, members in index.items():
        if len(members) > max_block:
            continue
        for i, j in combinations(members, 2):
            if (i, j) in seen:
                continue
            union = token_sets[i] | token_sets[j]
            overlap = len(token_sets[i] & token_sets[j]) / len(union) if union else 0.0
            if overlap >= min_overlap or (first_tokens[i] and first_tokens[i] == first_tokens[j]):
                seen[(i, j)] = overlap
    ranked = sorted(seen.items(), key=lambda item: -item[1])[:max_pairs]
    return [(i, j, overlap) for (i, j), overlap in ranked]


def judge_batch(batch: list[tuple[int, int, float]], records: list[dict], fields: list[str]) -> list[float]:
    state = {"pairs": [{"a": {f: records[i].get(f) for f in fields}, "b": {f: records[j].get(f) for f in fields}} for i, j, _ in batch]}
    questions = {
        f"pair_{n}": noul(
            f"Do `pairs[{n}].a` and `pairs[{n}].b` describe the same real-world entity? "
            "Differences in case, spelling, punctuation, or suffixes such as Inc or LLC, or a missing word, "
            "can still be the same entity. A different location, person, number, or ID means a different entity.",
            true="The two records are the same entity and can be merged.",
            false="The two records are different entities.",
        )
        for n in range(len(batch))
    }
    answers = ask(state, questions)
    return [answers[f"pair_{n}"]["noul"] for n in range(len(batch))]


def merge_groups(pairs: list[dict], count: int, threshold: float) -> list[list[int]]:
    parent = list(range(count))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for pair in pairs:
        if pair["p_same"] >= threshold:
            parent[find(pair["a"])] = find(pair["b"])
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(count):
        groups[find(i)].append(i)
    return [sorted(g) for g in groups.values() if len(g) > 1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", help="CSV, JSON (list of objects), or JSONL file.")
    parser.add_argument("--fields", nargs="+", required=True, help="Fields that identify an entity, ex. name city.")
    parser.add_argument("--id-field", help="Field with a record ID. Default: the row number.")
    parser.add_argument("--threshold", type=float, default=0.95, help="Minimum P(same) to merge.")
    parser.add_argument("--uncertain-low", type=float, default=0.5, help="Pairs from this value up to the threshold are listed for review.")
    parser.add_argument("--min-overlap", type=float, default=0.25, help="Minimum word overlap for a candidate pair.")
    parser.add_argument("--max-block", type=int, default=200, help="Ignore words shared by more records than this.")
    parser.add_argument("--max-pairs", type=int, default=5000)
    parser.add_argument("--batch", type=int, default=25, help="Pairs per Jev request.")
    parser.add_argument("--out", default="dedupe-plan.json", help="Merge plan (JSON).")
    parser.add_argument("--csv", help="Also write all judged pairs to this CSV file.")
    args = parser.parse_args()

    input_path = Path(args.input)
    records = load_records(input_path)
    missing = [f for f in args.fields if not any(f in r for r in records[:50])]
    if missing:
        print(f"Fields not found in the records: {', '.join(missing)}", file=sys.stderr)
        return 1

    def record_id(i: int):
        return records[i].get(args.id_field) if args.id_field else i

    started = time.perf_counter()
    candidates = candidate_pairs(records, args.fields, args.min_overlap, args.max_block, args.max_pairs)
    if not candidates:
        print("No candidate pairs. Lower --min-overlap or use other --fields.", file=sys.stderr)
        return 1
    batches = [candidates[i : i + args.batch] for i in range(0, len(candidates), args.batch)]
    try:
        with ThreadPoolExecutor(max_workers=min(8, len(batches))) as pool:
            results = list(pool.map(lambda b: judge_batch(b, records, args.fields), batches))
    except JevError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    elapsed = time.perf_counter() - started

    pairs = []
    for batch, probabilities in zip(batches, results):
        for (i, j, overlap), p in zip(batch, probabilities):
            pairs.append({"a": i, "b": j, "overlap": round(overlap, 3), "p_same": round(p, 4)})
    pairs.sort(key=lambda pair: -pair["p_same"])

    groups = merge_groups(pairs, len(records), args.threshold)
    uncertain = [p for p in pairs if args.uncertain_low <= p["p_same"] < args.threshold]

    def view(i: int) -> dict:
        return {"id": record_id(i), **{f: records[i].get(f) for f in args.fields}}

    plan = {
        "input": str(input_path),
        "fields": args.fields,
        "threshold": args.threshold,
        "records": len(records),
        "candidate_pairs": len(pairs),
        "seconds": round(elapsed, 2),
        "groups": [
            {
                "records": [view(i) for i in group],
                "pairs": [{"a": record_id(p["a"]), "b": record_id(p["b"]), "p_same": p["p_same"]} for p in pairs if p["a"] in group and p["b"] in group and p["p_same"] >= args.threshold],
            }
            for group in groups
        ],
        "uncertain": [{"a": view(p["a"]), "b": view(p["b"]), "p_same": p["p_same"]} for p in uncertain],
    }
    Path(args.out).write_text(json.dumps(plan, indent=2, default=str), encoding="utf-8")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["a_id", "b_id", "p_same", "overlap", *[f"a_{f}" for f in args.fields], *[f"b_{f}" for f in args.fields]])
            for p in pairs:
                writer.writerow([record_id(p["a"]), record_id(p["b"]), p["p_same"], p["overlap"],
                                 *[records[p["a"]].get(f) for f in args.fields], *[records[p["b"]].get(f) for f in args.fields]])

    print(f"{len(records)} records, {len(pairs)} candidate pairs judged in {elapsed:.2f}s.")
    print(f"{len(groups)} merge groups at p >= {args.threshold}. {len(uncertain)} uncertain pairs to review.")
    print(f"Plan written to {args.out}. The input file was not changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
