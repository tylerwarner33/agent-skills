"""Stop hook: before Claude stops, Jev checks each checklist item against the evidence.

Checklist source (first found):
  1. <project>/.claude/jev-checklist.md  (each bullet or numbered line is one item)
  2. The latest TodoWrite list in the session transcript

Evidence: the last assistant messages, `git diff --stat`, and the start of `git diff`.

Settings (environment variables):
  JEV_CHECKLIST_NOT_DONE_BELOW  default 0.3  An item below this blocks the stop.
  JEV_CHECKLIST_DONE_AT         default 0.7  An item below this (and not blocked) is listed as uncertain.
  JEV_CHECKLIST_MAX_BLOCKS      default 3    Stop blocking after this many blocks in one session.

Test without Claude Code:
  echo '{"transcript_path": "t.jsonl", "cwd": ".", "stop_hook_active": false}' | python checklist_hook.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "jev-setup" / "scripts"))
from jev_client import JevError, ask, noul  # noqa: E402

CHECKLIST_PATH = Path(".claude") / "jev-checklist.md"
STATE_PATH = Path(".claude") / "jev-checklist-state.json"
RULE_LINE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?(.+\S)\s*$")
LAST_MESSAGES = 3
MAX_MESSAGE_CHARS = 4_000
MAX_DIFF_CHARS = 20_000


def read_transcript(path: str | None) -> list[dict]:
    if not path or not Path(path).is_file():
        return []
    entries = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Sidechain entries are subagent messages, not the main session.
        if isinstance(entry, dict) and not entry.get("isSidechain"):
            entries.append(entry)
    return entries


def content_blocks(entry: dict) -> list:
    message = entry.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return content if isinstance(content, list) else []


def latest_todos(entries: list[dict]) -> list[str]:
    for entry in reversed(entries):
        for block in content_blocks(entry):
            if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "TodoWrite":
                todos = (block.get("input") or {}).get("todos") or []
                items = [t.get("content") for t in todos if isinstance(t, dict) and t.get("content")]
                if items:
                    return items
    return []


def last_assistant_texts(entries: list[dict]) -> list[str]:
    texts = []
    for entry in reversed(entries):
        if entry.get("type") != "assistant":
            continue
        text = "\n".join(b.get("text", "") for b in content_blocks(entry) if isinstance(b, dict) and b.get("type") == "text").strip()
        if text:
            texts.append(text[-MAX_MESSAGE_CHARS:])
        if len(texts) >= LAST_MESSAGES:
            break
    return list(reversed(texts))


def git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout if result.returncode == 0 else ""


def read_checklist(root: Path, entries: list[dict]) -> tuple[list[str], str]:
    path = root / CHECKLIST_PATH
    if path.is_file():
        items = [m.group(1) for m in map(RULE_LINE.match, path.read_text(encoding="utf-8").splitlines()) if m]
        if items:
            return items, CHECKLIST_PATH.as_posix()
    return latest_todos(entries), "todo list"


def block_count(root: Path, session: str) -> int:
    try:
        state = json.loads((root / STATE_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    return state.get(session, 0) if isinstance(state, dict) else 0


def save_block_count(root: Path, session: str, count: int) -> None:
    try:
        (root / STATE_PATH).parent.mkdir(parents=True, exist_ok=True)
        (root / STATE_PATH).write_text(json.dumps({session: count}), encoding="utf-8")
    except OSError:
        pass


def main() -> int:
    event = json.load(sys.stdin)
    if event.get("stop_hook_active"):
        return 0  # Claude is already continuing because of a stop hook. Do not loop.

    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or ".")
    session = str(event.get("session_id") or "default")
    max_blocks = int(os.environ.get("JEV_CHECKLIST_MAX_BLOCKS", "3"))
    if block_count(root, session) >= max_blocks:
        return 0

    entries = read_transcript(event.get("transcript_path"))
    items, source = read_checklist(root, entries)
    if not items:
        return 0

    evidence = {
        "final_messages": last_assistant_texts(entries),
        "diff_stat": git(root, "diff", "HEAD", "--stat")[:4_000],
        "diff": git(root, "diff", "HEAD")[:MAX_DIFF_CHARS],
    }
    questions = {
        f"item_{i}": noul(
            f"Does `evidence` show that this checklist item is done? Item: {item}",
            true="The evidence shows that the item is done.",
            false="The evidence does not show that the item is done.",
        )
        for i, item in enumerate(items)
    }
    try:
        answers = ask({"checklist": items, "evidence": evidence}, questions, timeout=20)
    except JevError as error:
        print(f"jev-task-checklist skipped: {error}", file=sys.stderr)
        return 0

    not_done_below = float(os.environ.get("JEV_CHECKLIST_NOT_DONE_BELOW", "0.3"))
    done_at = float(os.environ.get("JEV_CHECKLIST_DONE_AT", "0.7"))
    missing, uncertain = [], []
    for i, item in enumerate(items):
        p = answers[f"item_{i}"]["noul"]
        if p < not_done_below:
            missing.append((item, p))
        elif p < done_at:
            uncertain.append((item, p))
    if not missing:
        if uncertain:
            print(f"jev-task-checklist: {len(uncertain)} item(s) uncertain.", file=sys.stderr)
        return 0

    lines = [f"jev-task-checklist: the evidence does not show these items from the {source} as done:"]
    lines += [f"- {item} (p_done={p:.2f})" for item, p in missing]
    if uncertain:
        lines.append("Uncertain (check them too):")
        lines += [f"- {item} (p_done={p:.2f})" for item, p in uncertain]
    lines.append("Finish these items, or tell the user why an item is not necessary. Then stop.")
    save_block_count(root, session, block_count(root, session) + 1)
    print(json.dumps({"decision": "block", "reason": "\n".join(lines)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
