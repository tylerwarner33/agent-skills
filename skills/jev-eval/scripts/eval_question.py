"""Test one Jev question against labeled cases before you trust its threshold.

  python eval_question.py --question question.json --cases cases.jsonl

question.json: one question object, ex.
  {"type": "noul", "instructions": "Is this command irreversible?", "criteria": {"true": "...", "false": "..."}}
cases.jsonl: one case per line, ex.
  {"state": {"command": "git push --force origin main"}, "label": true}
  Labels: true/false for noul, an option name for choice, a level index (0, 1, ...) for score.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "jev-setup" / "scripts"))
from jev_client import JevError, ask  # noqa: E402

THRESHOLDS = [round(0.1 * i, 1) for i in range(1, 10)]


def run_case(question: dict, case: dict) -> dict:
    started = time.perf_counter()
    try:
        answer = ask(case["state"], {"q": question})["q"]
        error = None
    except JevError as exc:
        answer, error = None, str(exc)
    return {"case": case, "answer": answer, "error": error, "seconds": time.perf_counter() - started}


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]


def short(state, limit: int = 100) -> str:
    text = state if isinstance(state, str) else json.dumps(state, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def eval_noul(results: list[dict], threshold: float | None, misses: int) -> dict:
    rows = [(bool(r["case"]["label"]), r["answer"]["noul"], r) for r in results]
    sweep = []
    for t in THRESHOLDS:
        tp = sum(1 for label, p, _ in rows if p >= t and label)
        fp = sum(1 for label, p, _ in rows if p >= t and not label)
        fn = sum(1 for label, p, _ in rows if p < t and label)
        tn = len(rows) - tp - fp - fn
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        sweep.append({"threshold": t, "accuracy": (tp + tn) / len(rows), "precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn, "tn": tn})
    best = max(sweep, key=lambda s: (s["accuracy"], s["f1"]))
    chosen = next((s for s in sweep if s["threshold"] == threshold), best) if threshold is not None else best
    worst = sorted(rows, key=lambda row: -abs(row[1] - (1.0 if row[0] else 0.0)))
    worst = [{"label": label, "p": round(p, 3), "state": short(r["case"]["state"])} for label, p, r in worst[:misses] if (p >= chosen["threshold"]) != label]
    return {"sweep": sweep, "best_threshold": best["threshold"], "chosen": chosen, "worst_misses": worst}


def eval_choice(results: list[dict], misses: int) -> dict:
    rows = [(str(r["case"]["label"]), r["answer"]["choice"], r["answer"].get("confidence", 0.0), r) for r in results]
    correct = sum(1 for label, pick, _, _ in rows if label == pick)
    buckets = []
    for low, high in ((0.8, 1.01), (0.5, 0.8), (0.0, 0.5)):
        inside = [row for row in rows if low <= row[2] < high]
        if inside:
            buckets.append({"confidence": f"{low:.1f}-{min(high, 1.0):.1f}", "cases": len(inside), "accuracy": sum(1 for row in inside if row[0] == row[1]) / len(inside)})
    confusion = Counter(f"{label} -> {pick}" for label, pick, _, _ in rows if label != pick)
    wrong = sorted((row for row in rows if row[0] != row[1]), key=lambda row: -row[2])
    worst = [{"label": label, "pick": pick, "confidence": round(conf, 3), "state": short(r["case"]["state"])} for label, pick, conf, r in wrong[:misses]]
    return {"accuracy": correct / len(rows), "by_confidence": buckets, "top_confusions": confusion.most_common(10), "worst_misses": worst}


def eval_score(results: list[dict], misses: int) -> dict:
    rows = [(int(r["case"]["label"]), r["answer"]["score"], r) for r in results]
    exact = sum(1 for label, s, _ in rows if round(s) == label)
    mae = statistics.mean(abs(s - label) for label, s, _ in rows)
    worst = sorted(rows, key=lambda row: -abs(row[1] - row[0]))
    worst = [{"label": label, "score": round(s, 2), "state": short(r["case"]["state"])} for label, s, r in worst[:misses] if round(s) != label]
    return {"accuracy": exact / len(rows), "mean_abs_error": mae, "worst_misses": worst}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--question", required=True, help="JSON file with one question object.")
    parser.add_argument("--cases", required=True, help="JSONL file with labeled cases.")
    parser.add_argument("--threshold", type=float, help="noul only: the threshold to report in detail. Default: the best one.")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--misses", type=int, default=10, help="Number of worst misses to list.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    question = json.loads(Path(args.question).read_text(encoding="utf-8"))
    cases = [json.loads(line) for line in Path(args.cases).read_text(encoding="utf-8").splitlines() if line.strip()]
    kind = question.get("type")
    if kind not in ("noul", "choice", "score"):
        print("The question type must be noul, choice, or score.", file=sys.stderr)
        return 1
    if not cases or any("state" not in c or "label" not in c for c in cases):
        print("Each case needs a state and a label.", file=sys.stderr)
        return 1

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda c: run_case(question, c), cases))
    total = time.perf_counter() - started

    failed = [r for r in results if r["error"]]
    results = [r for r in results if not r["error"]]
    if not results:
        print(f"FAIL: all {len(failed)} requests failed. First error: {failed[0]['error']}", file=sys.stderr)
        return 1

    labels = Counter(str(r["case"]["label"]).lower() if kind == "noul" else str(r["case"]["label"]) for r in results)
    majority, majority_count = labels.most_common(1)[0]
    latencies = [r["seconds"] for r in results]
    report = {
        "type": kind,
        "cases": len(results),
        "failed_requests": len(failed),
        "label_counts": dict(labels),
        "baseline": {"always": majority, "accuracy": majority_count / len(results)},
        "latency": {"p50": percentile(latencies, 0.5), "p95": percentile(latencies, 0.95), "total_seconds": total},
    }
    if kind == "noul":
        report.update(eval_noul(results, args.threshold, args.misses))
    elif kind == "choice":
        report.update(eval_choice(results, args.misses))
    else:
        report.update(eval_score(results, args.misses))

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print(f"{kind}: {len(results)} cases ({len(failed)} failed requests). Labels: {dict(labels)}")
    print(f"Baseline (always '{majority}'): accuracy {report['baseline']['accuracy']:.3f}")
    print(f"Latency: p50 {report['latency']['p50']:.3f}s, p95 {report['latency']['p95']:.3f}s, total {total:.2f}s")
    if kind == "noul":
        print("\nthreshold  accuracy  precision  recall  f1     tp   fp   fn   tn")
        for s in report["sweep"]:
            print(f"{s['threshold']:<9}  {s['accuracy']:.3f}     {s['precision']:.3f}      {s['recall']:.3f}   {s['f1']:.3f}  {s['tp']:<4} {s['fp']:<4} {s['fn']:<4} {s['tn']}")
        print(f"\nBest threshold by accuracy: {report['best_threshold']}")
        chosen = report["chosen"]
        print(f"At {chosen['threshold']}: accuracy {chosen['accuracy']:.3f} vs baseline {report['baseline']['accuracy']:.3f}")
    elif kind == "choice":
        print(f"Accuracy: {report['accuracy']:.3f}")
        for b in report["by_confidence"]:
            print(f"  confidence {b['confidence']}: {b['cases']} cases, accuracy {b['accuracy']:.3f}")
        for pair, count in report["top_confusions"]:
            print(f"  confused {pair}: {count}")
    else:
        print(f"Exact accuracy: {report['accuracy']:.3f}, mean absolute error {report['mean_abs_error']:.3f}")
    if report["worst_misses"]:
        print("\nWorst misses:")
        for miss in report["worst_misses"]:
            print(f"  {miss}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
