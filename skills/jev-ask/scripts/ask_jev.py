"""Ask Jev questions about files or text, without reading them into Claude's context.

Each file is one request. All questions about that file go in the same request.
Requests run in parallel.

  # yes/no over a glob
  python ask_jev.py --files "src/**/*.ts" --yes-no "Does this file contain a TODO or a known shortcut?" --min 0.5

  # two questions per file
  python ask_jev.py --files src/auth/*.ts \
    --yes-no "Does this file touch authentication?" \
    --choice "Which layer is this file?" --options http="HTTP handler" domain="Domain logic" data="Data access"

  # classify command output
  npm test 2>&1 | python ask_jev.py --stdin \
    --choice "What kind of failure is this?" --options bug="A real bug" flaky="A flaky or timing test" env="Setup or environment" none="All tests pass"
"""

from __future__ import annotations

import argparse
import fnmatch
import glob
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "jev-setup" / "scripts"))
from jev_client import JevError, ask, choice, noul, score  # noqa: E402

SECRET_PATTERNS = [".env", ".env.*", "*.pem", "*.key", "*.pfx", "*.p12", "id_rsa*", "id_ed25519*", "*credentials*", "*secret*"]
SKIP_DIRS = {".git", "node_modules", "bin", "obj", "dist", "build", ".venv", "venv", "__pycache__"}


def parse_options(values: list[str]) -> dict[str, str]:
    options = {}
    for value in values:
        key, _, description = value.partition("=")
        options[key.strip()] = description.strip() or key.strip()
    return options


def build_questions(args) -> tuple[dict, dict]:
    """Return (questions, labels). The question text points at `content`."""
    questions, labels = {}, {}
    for i, text in enumerate(args.yes_no or [], 1):
        questions[f"yn{i}"] = noul(f"About `content` (from `source`): {text}")
        labels[f"yn{i}"] = text
    if args.choice:
        if not args.options:
            sys.exit("--choice needs --options key=description ...")
        questions["choice"] = choice(f"About `content` (from `source`): {args.choice}", parse_options(args.options))
        labels["choice"] = args.choice
    if args.score:
        if not args.levels or len(args.levels) < 2:
            sys.exit("--score needs 2 to 10 --levels, lowest first.")
        questions["score"] = score(f"About `content` (from `source`): {args.score}", args.levels)
        labels["score"] = args.score
    if not questions:
        sys.exit("Give at least one --yes-no, --choice, or --score question.")
    return questions, labels


def is_secret(path: Path) -> bool:
    return any(fnmatch.fnmatch(path.name.lower(), pattern) for pattern in SECRET_PATTERNS)


def collect_files(patterns: list[str], allow_secrets: bool) -> tuple[list[Path], list[str]]:
    files, skipped = [], []
    for pattern in patterns:
        matches = glob.glob(pattern, recursive=True) or [pattern]
        for name in sorted(matches):
            path = Path(name)
            if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
                continue
            if is_secret(path) and not allow_secrets:
                skipped.append(path.as_posix())
                continue
            if path not in files:
                files.append(path)
    return files, skipped


def summarize(answer: dict) -> dict:
    if answer["type"] == "noul":
        return {"p_yes": round(answer["noul"], 3)}
    if answer["type"] == "choice":
        return {"choice": answer["choice"], "confidence": round(answer.get("confidence", 0.0), 3)}
    return {"score": round(answer["score"], 3), "confidence": round(answer.get("confidence", 0.0), 3)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--files", nargs="+", help="Paths or globs. Use ** for recursive globs.")
    source.add_argument("--text", help="Text to judge.")
    source.add_argument("--stdin", action="store_true", help="Read the text to judge from stdin.")
    parser.add_argument("--yes-no", action="append", help="A yes/no question. Repeat for more.")
    parser.add_argument("--choice", help="A question with one answer from --options.")
    parser.add_argument("--options", nargs="+", help="key=description pairs for --choice. Add a none option if nothing may fit.")
    parser.add_argument("--score", help="A question rated on --levels.")
    parser.add_argument("--levels", nargs="+", help="2 to 10 level descriptions for --score, lowest first.")
    parser.add_argument("--max-chars", type=int, default=24_000, help="Characters sent per file. Long inputs lower accuracy.")
    parser.add_argument("--min", type=float, help="Show only files with a yes/no probability at or above this value.")
    parser.add_argument("--allow-secrets", action="store_true", help="Also send files that look like secrets.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    questions, labels = build_questions(args)

    if args.files:
        files, skipped = collect_files(args.files, args.allow_secrets)
        if skipped:
            print(f"Skipped {len(skipped)} file(s) that look like secrets: {', '.join(skipped)}", file=sys.stderr)
        items = []
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            items.append((path.as_posix(), text))
    else:
        items = [("stdin" if args.stdin else "text", sys.stdin.read() if args.stdin else args.text)]
    if not items:
        print("No files matched.", file=sys.stderr)
        return 1

    def run(item):
        name, text = item
        truncated = len(text) > args.max_chars
        answers = ask({"source": name, "content": text[: args.max_chars]}, questions)
        row = {"source": name, "truncated": truncated}
        row.update({key: summarize(answers[key]) for key in questions})
        return row

    started = time.perf_counter()
    try:
        with ThreadPoolExecutor(max_workers=min(8, len(items))) as pool:
            rows = list(pool.map(run, items))
    except JevError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    elapsed = time.perf_counter() - started

    if args.min is not None:
        rows = [r for r in rows if any(r[k].get("p_yes", 0) >= args.min for k in questions if k.startswith("yn"))]

    if args.json:
        print(json.dumps({"questions": labels, "seconds": round(elapsed, 2), "results": rows}, indent=2))
        return 0

    print(f"{len(items)} item(s) in {elapsed:.2f}s")
    for key, text in labels.items():
        print(f"  {key}: {text}")
    for row in rows:
        parts = []
        for key in questions:
            value = row[key]
            if "p_yes" in value:
                parts.append(f"{key}={value['p_yes']:.2f}")
            elif "choice" in value:
                parts.append(f"{key}={value['choice']} ({value['confidence']:.2f})")
            else:
                parts.append(f"{key}={value['score']:.2f} ({value['confidence']:.2f})")
        note = "  [truncated]" if row["truncated"] else ""
        print(f"{row['source']}: {'  '.join(parts)}{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
