"""PreToolUse hook: block an edit if Jev is sure that it breaks a rule for that file.

Reads rules from <project>/.claude/jev-rules.json:
  {
    "threshold": 0.8,
    "failClosed": false,
    "rules": [
      {"paths": ["src/client/**"], "rules": ["Never read employee data directly in the browser."]},
      {"paths": ["src/api/**"], "rulesFile": "docs/rules/api.md"}
    ]
  }

Test without Claude Code:
  echo '{"tool_name":"Write","tool_input":{"file_path":"src/client/x.ts","content":"..."},"cwd":"."}' | python rule_enforcer_hook.py
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "jev-setup" / "scripts"))
from jev_client import JevError, ask, noul  # noqa: E402

CONFIG_PATH = Path(".claude") / "jev-rules.json"
RULE_LINE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+\S)\s*$")
MAX_CHANGE_CHARS = 30_000


def rules_for(relative: str, config: dict, root: Path) -> list[str]:
    rules: list[str] = []
    for entry in config.get("rules", []):
        if not any(fnmatch.fnmatch(relative, pattern) for pattern in entry.get("paths", [])):
            continue
        rules.extend(entry.get("rules", []))
        rules_file = entry.get("rulesFile")
        if rules_file:
            for line in (root / rules_file).read_text(encoding="utf-8").splitlines():
                match = RULE_LINE.match(line)
                if match:
                    rules.append(match.group(1))
    return list(dict.fromkeys(rules))


def describe_change(tool_name: str, tool_input: dict) -> dict:
    if tool_name == "Write":
        return {"kind": "write whole file", "new_content": tool_input.get("content", "")[:MAX_CHANGE_CHARS]}
    if tool_name == "Edit":
        return {"kind": "replace text", "old_text": tool_input.get("old_string", ""), "new_text": tool_input.get("new_string", "")}
    if tool_name == "MultiEdit":
        edits = [{"old_text": e.get("old_string", ""), "new_text": e.get("new_string", "")} for e in tool_input.get("edits", [])]
        return {"kind": "several replacements", "edits": edits}
    return {"kind": tool_name, "input": json.dumps(tool_input)[:MAX_CHANGE_CHARS]}


def deny(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))


def main() -> int:
    event = json.load(sys.stdin)
    tool_input = event.get("tool_input") or {}
    file_path = tool_input.get("file_path")
    if not file_path:
        return 0

    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or ".")
    config_file = root / CONFIG_PATH
    if not config_file.is_file():
        return 0
    config = json.loads(config_file.read_text(encoding="utf-8"))
    fail_closed = bool(config.get("failClosed", False))

    try:
        relative = Path(file_path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return 0

    try:
        rules = rules_for(relative, config, root)
    except OSError as error:
        print(f"jev-rule-enforcer: cannot read rules: {error}", file=sys.stderr)
        return 0
    if not rules:
        return 0

    state = {"file_path": relative, "change": describe_change(event.get("tool_name", ""), tool_input)}
    questions = {
        f"rule_{i}": noul(
            f"Does the change in `change` to the file `file_path` break this rule? Rule: {rule}",
            true="The change breaks the rule.",
            false="The change follows the rule, or the rule does not apply to this change.",
        )
        for i, rule in enumerate(rules)
    }

    try:
        answers = ask(state, questions, timeout=15)
    except JevError as error:
        if fail_closed:
            deny(f"jev-rule-enforcer could not check the rules for {relative}: {error}")
        else:
            print(f"jev-rule-enforcer skipped: {error}", file=sys.stderr)
        return 0

    threshold = float(config.get("threshold", 0.8))
    ask_at = float(config.get("askAt", 0.5))
    probabilities = [(rules[i], answers[f"rule_{i}"]["noul"]) for i in range(len(rules))]
    broken = [(rule, p) for rule, p in probabilities if p >= threshold]
    unsure = [(rule, p) for rule, p in probabilities if ask_at <= p < threshold]

    if broken:
        lines = [f"Blocked by jev-rule-enforcer. The edit to {relative} breaks these project rules:"]
        lines += [f"- {rule} (p={p:.2f})" for rule, p in broken]
        lines.append("Change the edit so that it follows the rules. If a rule is wrong, ask the user.")
        deny("\n".join(lines))
    elif unsure:
        reason = f"jev-rule-enforcer is not sure that the edit to {relative} follows these rules: " + "; ".join(
            f"{rule} (p={p:.2f})" for rule, p in unsure
        )
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
