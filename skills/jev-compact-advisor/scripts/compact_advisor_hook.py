"""UserPromptSubmit hook: Jev decides if now is a good time to compact or clear.

The hook estimates the context size from the transcript. Above the lower band, it asks Jev:
  - Is the new prompt a different task from the recent work?
  - Is the recent work finished?
Then it shows the user a message that recommends /compact or /clear. It never blocks the prompt.

Bands (fraction of the context window):
  notice     >= 0.40  message only if the task changes
  recommend  >= 0.60  message only if the task changes
  request    >= 0.80  message always

Settings (environment variables):
  JEV_COMPACT_WINDOW_TOKENS  default 200000
  JEV_COMPACT_BANDS          default "0.4,0.6,0.8"
  JEV_COMPACT_SWITCH_AT      default 0.6

Test without Claude Code:
  echo '{"prompt": "now fix the login page", "transcript_path": "t.jsonl"}' | python compact_advisor_hook.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "jev-setup" / "scripts"))
from jev_client import JevError, ask, noul  # noqa: E402

CHARS_PER_TOKEN = 4
RECENT_PROMPTS = 3
MAX_PROMPT_CHARS = 1_500
MAX_SUMMARY_CHARS = 3_000


def read_entries(path: str | None) -> list[dict]:
    if not path or not Path(path).is_file():
        return []
    entries = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Sidechain entries are subagent messages. They are not in the main context.
        if isinstance(entry, dict) and not entry.get("isSidechain"):
            entries.append(entry)
    # Count only the entries after the last compaction.
    for index in range(len(entries) - 1, -1, -1):
        entry = entries[index]
        if entry.get("subtype") == "compact_boundary" or entry.get("isCompactSummary"):
            return entries[index:]
    return entries


def blocks(entry: dict) -> list:
    message = entry.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return content if isinstance(content, list) else []


def block_chars(block) -> int:
    if not isinstance(block, dict):
        return len(str(block))
    if block.get("type") == "text":
        return len(block.get("text", ""))
    if block.get("type") == "tool_use":
        return len(json.dumps(block.get("input", {})))
    if block.get("type") == "tool_result":
        content = block.get("content")
        if isinstance(content, list):
            return sum(block_chars(b) for b in content)
        return len(str(content or ""))
    return 0


def estimate_tokens(entries: list[dict]) -> int:
    """An approximate count: message characters divided by 4."""
    return sum(block_chars(b) for e in entries for b in blocks(e)) // CHARS_PER_TOKEN


def text_of(entry: dict) -> str:
    return "\n".join(b.get("text", "") for b in blocks(entry) if isinstance(b, dict) and b.get("type") == "text").strip()


def recent_work(entries: list[dict]) -> dict:
    prompts, summary = [], ""
    for entry in reversed(entries):
        text = text_of(entry)
        if not text:
            continue
        if entry.get("type") == "assistant" and not summary:
            summary = text[-MAX_SUMMARY_CHARS:]
        elif entry.get("type") == "user" and not entry.get("isMeta") and len(prompts) < RECENT_PROMPTS:
            prompts.append(text[:MAX_PROMPT_CHARS])
        if summary and len(prompts) >= RECENT_PROMPTS:
            break
    return {"recent_user_prompts": list(reversed(prompts)), "last_assistant_message": summary}


def main() -> int:
    event = json.load(sys.stdin)
    prompt = (event.get("prompt") or "").strip()
    if not prompt or prompt.startswith("/"):
        return 0

    window = int(os.environ.get("JEV_COMPACT_WINDOW_TOKENS", "200000"))
    notice, recommend, request = (float(x) for x in os.environ.get("JEV_COMPACT_BANDS", "0.4,0.6,0.8").split(","))
    switch_at = float(os.environ.get("JEV_COMPACT_SWITCH_AT", "0.6"))

    entries = read_entries(event.get("transcript_path"))
    used = estimate_tokens(entries) / window
    if used < notice:
        return 0
    level = "request" if used >= request else "recommend" if used >= recommend else "notice"

    state = {"new_prompt": prompt[:MAX_PROMPT_CHARS], "recent_work": recent_work(entries)}
    questions = {
        "switch": noul(
            "Is `new_prompt` a different task from `recent_work`? A follow-up, a fix, or a next step "
            "of the same work is not a different task.",
            true="The new prompt starts a different task.",
            false="The new prompt continues the same work.",
        ),
        "finished": noul(
            "Does `recent_work` show that the previous task is finished?",
            true="The previous task is finished.",
            false="The previous task is not finished.",
        ),
    }
    try:
        answers = ask(state, questions, timeout=10)
    except JevError as error:
        print(f"jev-compact-advisor skipped: {error}", file=sys.stderr)
        return 0

    p_switch = answers["switch"]["noul"]
    p_finished = answers["finished"]["noul"]
    switching = p_switch >= switch_at
    if not switching and level != "request":
        return 0

    size = f"Context is about {used:.0%} full (estimate)."
    if switching and p_finished >= switch_at:
        action = "The new prompt starts a different task and the previous task looks finished. Consider /clear, or /compact to keep a summary."
    elif switching:
        action = "The new prompt starts a different task. Consider /compact before you continue."
    else:
        action = "Consider /compact soon, at the next good break in the work."
    labels = {"notice": "Jev notice", "recommend": "Jev recommends compaction", "request": "Jev requests compaction"}
    message = f"{labels[level]}: {size} {action} (p_switch={p_switch:.2f}, p_finished={p_finished:.2f})"
    print(json.dumps({"systemMessage": message}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
