"""Find the files that answer a question: keyword search, then Jev ranking.

Step 1: A keyword search finds candidate files (ripgrep if found, else a Python scan).
Step 2: Jev scores the candidates 20 at a time, in parallel, on how closely each
        file matches the question.

  python rank_files.py --query "where is the session timeout set" --keywords session timeout expire
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "jev-setup" / "scripts"))
from jev_client import JevError, ask, score  # noqa: E402

SKIP_DIRS = {".git", "node_modules", "bin", "obj", "dist", "build", ".venv", "venv", "__pycache__", ".next", "coverage"}
STOP_WORDS = {"where", "what", "which", "does", "with", "that", "this", "from", "file", "files", "code", "find", "show", "have", "there", "about", "into", "when", "make", "used", "uses"}
MAX_MATCH_LINES = 15
HEAD_LINES = 8
MAX_LINE_CHARS = 200

LEVELS = [
    "Not related: the file has nothing to do with the question.",
    "Weak: the file mentions a related term, but does not contain what the question asks about.",
    "Related: the file uses or calls what the question asks about, but does not define or handle it.",
    "Strong: the file contains a main part of the answer to the question.",
    "Exact: this is the file the question is about. It defines or handles exactly what the question asks.",
]


def default_keywords(query: str) -> list[str]:
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", query)
    return [w for w in dict.fromkeys(w.lower() for w in words) if w not in STOP_WORDS]


def search_ripgrep(root: Path, keywords: list[str]) -> dict[str, int]:
    command = ["rg", "--count-matches", "--ignore-case", "--fixed-strings"]
    for skip in SKIP_DIRS:
        command += ["--glob", f"!{skip}"]
    for keyword in keywords:
        command += ["-e", keyword]
    command.append(str(root))
    output = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    hits = {}
    for line in output.splitlines():
        path, _, count = line.rpartition(":")
        if path and count.isdigit():
            hits[path] = int(count)
    return hits


def search_python(root: Path, keywords: list[str]) -> dict[str, int]:
    lowered = [k.lower() for k in keywords]
    hits = {}
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            path = Path(folder) / name
            try:
                text = path.read_text(encoding="utf-8").lower()
            except (UnicodeDecodeError, OSError):
                continue
            count = sum(text.count(k) for k in lowered)
            if count:
                hits[str(path)] = count
    return hits


def excerpt(path: str, keywords: list[str]) -> str:
    """The first lines of the file, plus the lines that contain a keyword."""
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    lowered = [k.lower() for k in keywords]
    picked = list(range(min(HEAD_LINES, len(lines))))
    for number, line in enumerate(lines):
        if len(picked) >= HEAD_LINES + MAX_MATCH_LINES:
            break
        if number >= HEAD_LINES and any(k in line.lower() for k in lowered):
            picked.append(number)
    return "\n".join(f"{n + 1}: {lines[n][:MAX_LINE_CHARS]}" for n in picked)


def rank_batch(query: str, batch: list[dict]) -> list[dict]:
    questions = {
        f"file_{i}": score(
            f"How closely does the file in `files[{i}]` match `question`? "
            "Judge from its path and its excerpt.",
            LEVELS,
        )
        for i in range(len(batch))
    }
    answers = ask({"question": query, "files": batch}, questions)
    ranked = []
    for i, item in enumerate(batch):
        answer = answers[f"file_{i}"]
        ranked.append({"path": item["path"], "score": round(answer["score"], 3), "confidence": round(answer.get("confidence", 0.0), 3)})
    return ranked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--query", required=True, help="The question, in plain words.")
    parser.add_argument("--keywords", nargs="*", help="Search terms. Default: words from the query.")
    parser.add_argument("--root", default=".", help="Folder to search.")
    parser.add_argument("--top", type=int, default=5, help="Number of files to return.")
    parser.add_argument("--batch", type=int, default=20, help="Files per Jev request.")
    parser.add_argument("--max-candidates", type=int, default=100)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = Path(args.root)
    keywords = args.keywords or default_keywords(args.query)
    if not keywords:
        print("No keywords. Give --keywords.", file=sys.stderr)
        return 1

    started = time.perf_counter()
    hits = search_ripgrep(root, keywords) if shutil.which("rg") else search_python(root, keywords)
    candidates = sorted(hits, key=hits.get, reverse=True)[: args.max_candidates]
    if not candidates:
        print("No files matched the keywords. Try other keywords.", file=sys.stderr)
        return 1
    search_time = time.perf_counter() - started

    items = [{"path": Path(p).relative_to(root).as_posix() if Path(p).is_relative_to(root) else p, "excerpt": excerpt(p, keywords)} for p in candidates]
    batches = [items[i : i + args.batch] for i in range(0, len(items), args.batch)]
    try:
        with ThreadPoolExecutor(max_workers=min(8, len(batches))) as pool:
            ranked = [r for batch in pool.map(lambda b: rank_batch(args.query, b), batches) for r in batch]
    except JevError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    total_time = time.perf_counter() - started

    ranked.sort(key=lambda r: (r["score"], r["confidence"]), reverse=True)
    top = ranked[: args.top]
    if args.json:
        print(json.dumps({"keywords": keywords, "candidates": len(items), "seconds": round(total_time, 2), "top": top}, indent=2))
        return 0
    print(f"Ranked {len(items)} files in {total_time:.2f}s (search {search_time:.2f}s). Keywords: {', '.join(keywords)}")
    for r in top:
        print(f"{r['score']:.2f}  (conf {r['confidence']:.2f})  {r['path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
