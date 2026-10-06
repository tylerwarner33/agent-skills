"""Ask Jev which documented rules have no test.

CLI mode:
  python check_rule_coverage.py --rules docs/access-rules.md --tests "tests/**/*auth*" [--json]

Hook mode (PostToolUse on Edit|Write|MultiEdit):
  python check_rule_coverage.py --hook
  Reads .claude/jev-docs-checker.json from the project. Runs only when the edited
  file matches a "watch" pattern. Returns the report to Claude as additional context.
"""

from __future__ import annotations

import argparse
import fnmatch
import glob
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "jev-setup" / "scripts"))
from jev_client import JevError, ask, noul  # noqa: E402

RULE_LINE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+\S)\s*$")
MAX_GROUP_CHARS = 60_000
MAX_FILE_CHARS = 20_000
CONFIG_PATH = Path(".claude") / "jev-docs-checker.json"


def read_rules(path: Path) -> list[str]:
    """Each bullet or numbered line in the rules file is one rule."""
    rules = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = RULE_LINE.match(line)
        if match:
            rules.append(match.group(1))
    return rules


def collect_tests(root: Path, patterns: list[str]) -> list[dict]:
    files = []
    seen = set()
    for pattern in patterns:
        for name in sorted(glob.glob(str(root / pattern), recursive=True)):
            path = Path(name)
            if not path.is_file() or path in seen:
                continue
            seen.add(path)
            text = path.read_text(encoding="utf-8", errors="replace")
            files.append({"file": path.relative_to(root).as_posix(), "content": text[:MAX_FILE_CHARS]})
    return files


def group_tests(tests: list[dict]) -> list[list[dict]]:
    """Split the test files into groups that fit in one request."""
    groups, current, size = [], [], 0
    for test in tests:
        length = len(test["content"])
        if current and size + length > MAX_GROUP_CHARS:
            groups.append(current)
            current, size = [], 0
        current.append(test)
        size += length
    if current:
        groups.append(current)
    return groups


def check(rules: list[str], tests: list[dict], covered_at: float, missing_below: float) -> list[dict]:
    """Return one result per rule. A rule is covered if any test group covers it."""
    best = [0.0] * len(rules)
    best_file = [None] * len(rules)
    questions = {
        f"rule_{i}": noul(
            "Does at least one test in `tests` check this rule? The test must exercise "
            f"the rule, not only mention it. Rule: {rule}",
            true="A test in `tests` checks this rule.",
            false="No test in `tests` checks this rule.",
        )
        for i, rule in enumerate(rules)
    }
    for group in group_tests(tests):
        answers = ask({"tests": group}, questions)
        for i in range(len(rules)):
            probability = answers[f"rule_{i}"]["noul"]
            if probability > best[i]:
                best[i] = probability
                best_file[i] = ", ".join(t["file"] for t in group) if len(group) <= 3 else f"{len(group)} files"

    results = []
    for i, rule in enumerate(rules):
        if best[i] >= covered_at:
            status = "covered"
        elif best[i] < missing_below:
            status = "missing"
        else:
            status = "uncertain"
        results.append({"rule": rule, "status": status, "p_covered": round(best[i], 3), "evidence": best_file[i]})
    return results


def format_report(results: list[dict]) -> str:
    missing = [r for r in results if r["status"] == "missing"]
    uncertain = [r for r in results if r["status"] == "uncertain"]
    lines = [
        f"Jev rule coverage: {len(results) - len(missing) - len(uncertain)} covered, "
        f"{len(missing)} missing, {len(uncertain)} uncertain (of {len(results)} rules)."
    ]
    for label, group in (("MISSING", missing), ("UNCERTAIN", uncertain)):
        for r in group:
            lines.append(f"- {label} (p={r['p_covered']}): {r['rule']}")
    return "\n".join(lines)


def run_hook() -> int:
    event = json.load(sys.stdin)
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or ".")
    config_file = root / CONFIG_PATH
    if not config_file.is_file():
        return 0
    config = json.loads(config_file.read_text(encoding="utf-8"))

    file_path = (event.get("tool_input") or {}).get("file_path")
    if not file_path:
        return 0
    try:
        relative = Path(file_path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return 0
    if not any(fnmatch.fnmatch(relative, pattern) for pattern in config.get("watch", [])):
        return 0

    try:
        rules = read_rules(root / config["rules"])
        tests = collect_tests(root, config.get("tests", []))
        results = check(rules, tests, config.get("coveredAt", 0.6), config.get("missingBelow", 0.4))
    except (JevError, OSError, KeyError) as error:
        print(f"jev-docs-checker skipped: {error}", file=sys.stderr)
        return 0

    if all(r["status"] == "covered" for r in results):
        return 0
    context = (
        f"{format_report(results)}\n"
        f"You edited {relative}, which controls access. Tell the user which rules have no test. "
        "Offer to write the missing tests."
    )
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": context}}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--hook", action="store_true", help="Run as a Claude Code PostToolUse hook.")
    parser.add_argument("--rules", help="Markdown file. Each bullet line is one rule.")
    parser.add_argument("--tests", nargs="+", default=[], help="Glob patterns for test files.")
    parser.add_argument("--root", default=".", help="Project root.")
    parser.add_argument("--covered-at", type=float, default=0.6)
    parser.add_argument("--missing-below", type=float, default=0.4)
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a text report.")
    args = parser.parse_args()

    if args.hook:
        return run_hook()
    if not args.rules or not args.tests:
        parser.error("--rules and --tests are necessary in CLI mode.")

    root = Path(args.root)
    rules = read_rules(root / args.rules)
    tests = collect_tests(root, args.tests)
    if not rules:
        print("No rules found. Write each rule as a bullet line.", file=sys.stderr)
        return 1
    if not tests:
        print("No test files matched.", file=sys.stderr)
        return 1
    try:
        results = check(rules, tests, args.covered_at, args.missing_below)
    except JevError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(results, indent=2) if args.json else format_report(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
