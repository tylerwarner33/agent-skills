"""Jev answers seven yes/no questions about a change, to select the review depth.

  python triage_change.py                 # working tree + staged changes against HEAD
  python triage_change.py --staged        # staged changes only
  python triage_change.py --base main     # the branch against main
  python triage_change.py --diff-file change.patch

Result: "light" only if Jev says no to each question with high certainty.
Any yes, or any uncertain answer, gives "full".
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "jev-setup" / "scripts"))
from jev_client import JevError, ask, noul  # noqa: E402

MAX_DIFF_CHARS = 40_000
MAX_RULES_CHARS = 15_000
DEFAULT_RULE_FILES = ["CLAUDE.md", "AGENTS.md", ".github/copilot-instructions.md"]

QUESTIONS = {
    "breaks_rule": (
        "Does the change in `diff` break a project rule in `rules`?",
        "The change breaks at least one rule.",
        "The change follows all rules, or no rule applies.",
    ),
    "should_not_change": (
        "Does the change in `diff` edit something that must usually not be edited by hand, "
        "ex. generated code, vendored code, lock files, a migration that already shipped, or release configuration? "
        "Use `task` if it is given: also say yes if the change edits things outside the task.",
        "The change edits something it must not edit.",
        "The change edits only what the task needs.",
    ),
    "access_control": (
        "Does the change in `diff` affect authentication, authorization, roles, permissions, or who can access what?",
        None,
        None,
    ),
    "data_shape": (
        "Does the change in `diff` alter stored or exchanged data, ex. a database schema, a migration, "
        "a serialized format, or a file format?",
        None,
        None,
    ),
    "public_contract": (
        "Does the change in `diff` alter a contract that other code or users depend on, "
        "ex. a public API, an endpoint, a CLI option, an event, or an exported type?",
        None,
        None,
    ),
    "security_sensitive": (
        "Does the change in `diff` touch security-sensitive code, ex. secrets, cryptography, "
        "input validation, file system or shell access, or network calls?",
        None,
        None,
    ),
    "weakens_tests": (
        "Does the change in `diff` delete, skip, or weaken tests or assertions?",
        None,
        None,
    ),
}


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout


def read_diff(args) -> str:
    if args.diff_file:
        return Path(args.diff_file).read_text(encoding="utf-8", errors="replace")
    if args.staged:
        return git("diff", "--cached")
    if args.base:
        return git("diff", f"{args.base}...HEAD")
    return git("diff", "HEAD")


def read_rules(paths: list[str]) -> str:
    texts = []
    for name in paths:
        path = Path(name)
        if path.is_file():
            texts.append(f"# {name}\n{path.read_text(encoding='utf-8', errors='replace')}")
    return "\n\n".join(texts)[:MAX_RULES_CHARS]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--staged", action="store_true")
    source.add_argument("--base", help="Compare the current branch against this ref.")
    source.add_argument("--diff-file")
    parser.add_argument("--rules", nargs="*", help=f"Rule files. Default: {', '.join(DEFAULT_RULE_FILES)} if found.")
    parser.add_argument("--task", help="What the change was for, in one sentence.")
    parser.add_argument("--light-below", type=float, default=0.2, help="Each answer must be below this for a light review.")
    args = parser.parse_args()

    try:
        diff = read_diff(args)
    except (subprocess.CalledProcessError, OSError) as error:
        print(f"FAIL: cannot read the diff: {error}", file=sys.stderr)
        return 1
    if not diff.strip():
        print(json.dumps({"mode": "none", "reasons": ["The diff is empty. There is nothing to review."]}, indent=2))
        return 0

    reasons = []
    truncated = len(diff) > MAX_DIFF_CHARS
    if truncated:
        reasons.append(f"The diff is larger than {MAX_DIFF_CHARS} characters. Jev saw only part of it.")

    rules = read_rules(args.rules if args.rules is not None else DEFAULT_RULE_FILES)
    state = {"diff": diff[:MAX_DIFF_CHARS]}
    if rules:
        state["rules"] = rules
    if args.task:
        state["task"] = args.task

    questions = {}
    for key, (text, true, false) in QUESTIONS.items():
        if key == "breaks_rule" and not rules:
            continue
        questions[key] = noul(text, true=true, false=false)

    try:
        answers = ask(state, questions)
    except JevError as error:
        print(json.dumps({"mode": "full", "reasons": [f"Jev failed: {error}"]}, indent=2))
        return 0

    probabilities = {key: round(answer["noul"], 3) for key, answer in answers.items()}
    flagged = {key: p for key, p in probabilities.items() if p >= args.light_below}
    for key, p in sorted(flagged.items(), key=lambda item: -item[1]):
        label = "yes" if p >= 0.5 else "uncertain"
        reasons.append(f"{key}: {label} (p={p})")

    mode = "full" if flagged or truncated else "light"
    print(json.dumps({"mode": mode, "reasons": reasons, "answers": probabilities}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
