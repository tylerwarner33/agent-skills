"""PreToolUse hook for Bash: Jev rates how reversible a command is, and blocks or asks.

Questions (one request):
  reversibility  choice: read_only, reversible, irreversible
  destructive    noul: does the command intend to destroy data, history, or state?
  exfiltration   noul: does the command send local data or secrets to another place?

Policy (defaults; override in <project>/.claude/jev-bash-gate.json):
  {"denyAt": 0.8, "askAt": 0.5, "skipPatterns": ["^git (status|diff|log)\\b"], "notes": "..."}
  deny  if P(irreversible), P(destructive), or P(exfiltration) >= denyAt
  ask   if one of them >= askAt (Claude Code asks the user)
  else  no decision: the normal permission rules apply

Test without Claude Code:
  echo '{"tool_name":"Bash","tool_input":{"command":"git push --force origin main"},"cwd":"."}' | python bash_gate_hook.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "jev-setup" / "scripts"))
from jev_client import JevError, ask, choice, noul  # noqa: E402

CONFIG_PATH = Path(".claude") / "jev-bash-gate.json"
MAX_COMMAND_CHARS = 8_000

# Plain read-only commands skip the Jev call. Keep this list short and obvious.
DEFAULT_SKIP = [
    r"^(ls|pwd|cat|head|tail|wc|echo|which|whoami|date)(\s|$)",
    r"^git (status|diff|log|show|branch( --list)?|remote -v)(\s|$)",
    r"^(rg|grep) ",
]
# A pipe, redirect, chain, or substitution can hide a second command.
COMPOUND = re.compile(r"[|;&<>`]|\$\(")

REVERSIBILITY = {
    "read_only": "The command only reads or lists. It changes no files, state, or remote systems.",
    "reversible": "The command changes something, but it is easy to undo or to rebuild, ex. a build output, "
    "a cache, an installed dependency folder, or a local commit that is still in the history.",
    "irreversible": "The command changes or deletes something that cannot easily come back, ex. a force push, "
    "history rewrite, deleting source or user data, dropping a database, or changing a remote or shared system.",
}


def load_config(root: Path) -> dict:
    path = root / CONFIG_PATH
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print(f"jev-bash-gate: bad config, defaults used: {error}", file=sys.stderr)
    return {}


def decide(decision: str, reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}))


def main() -> int:
    event = json.load(sys.stdin)
    if event.get("tool_name") != "Bash":
        return 0
    tool_input = event.get("tool_input") or {}
    command = (tool_input.get("command") or "").strip()
    if not command:
        return 0

    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or ".")
    config = load_config(root)
    skip = config.get("skipPatterns", DEFAULT_SKIP)
    if not COMPOUND.search(command) and any(re.search(p, command) for p in skip):
        return 0

    state = {
        "command": command[:MAX_COMMAND_CHARS],
        "purpose": tool_input.get("description", ""),
        "working_directory": event.get("cwd", ""),
        "project_notes": config.get("notes", ""),
    }
    questions = {
        "reversibility": choice(
            "How reversible is the shell `command` if it runs in `working_directory`? "
            "Judge all parts of the command, including pipes and chained commands. Use `project_notes` if given.",
            REVERSIBILITY,
        ),
        "destructive": noul(
            "Does the shell `command` intend to delete, overwrite, or discard data, history, or state that "
            "matters, ex. source files, user data, git history, or a database?",
            true="The command is destructive.",
            false="The command does not destroy anything that matters.",
        ),
        "exfiltration": noul(
            "Does the shell `command` send local files, environment variables, keys, or secrets to another "
            "machine or service, ex. with curl, scp, or a webhook?",
            true="The command sends local data or secrets out.",
            false="The command sends no local data or secrets out.",
        ),
    }

    try:
        answers = ask(state, questions, timeout=10)
    except JevError as error:
        print(f"jev-bash-gate skipped: {error}", file=sys.stderr)
        return 0

    risks = {
        "irreversible": answers["reversibility"].get("probabilities", {}).get("irreversible", 0.0),
        "destructive intent": answers["destructive"]["noul"],
        "sends data out": answers["exfiltration"]["noul"],
    }
    deny_at = float(config.get("denyAt", 0.8))
    ask_at = float(config.get("askAt", 0.5))
    top_risk, top_p = max(risks.items(), key=lambda item: item[1])
    summary = ", ".join(f"{name} p={p:.2f}" for name, p in risks.items())

    if top_p >= deny_at:
        decide("deny", f"Blocked by jev-bash-gate ({summary}). Do not try another form of this command. "
                       "If it is necessary, explain why to the user and let the user run it.")
    elif top_p >= ask_at:
        decide("ask", f"jev-bash-gate is not sure this command is safe ({top_risk} p={top_p:.2f}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
