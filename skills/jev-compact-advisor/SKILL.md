---
name: jev-compact-advisor
description: Install a UserPromptSubmit hook in which Jev decides if now is a good time to compact or clear the session - when the context is large and the new prompt starts a different task, the user gets a notice, a recommendation, or a request to run /compact or /clear. Use when the user asks for advice on when to compact, wants to compact at task boundaries, or asks to set up the Jev compact advisor.
---

# Jev Compact Advisor

A good time to compact is when the work switches to a new task. Automatic compaction starts at a fixed size, often in the middle of a task. This hook watches each prompt. When the context is large, it asks Jev two yes/no questions:

1. Is the new prompt a different task from the recent work?
2. Is the recent work finished?

Then it shows the user a short message. The message recommends `/compact` or `/clear`. The hook never blocks the prompt.

Requires the `jev-setup` skill (a key in the environment). To make the compaction itself faster, see the `jev-fast-compaction` skill.

## Bands

The hook estimates how full the context is. Below the lower band, it does nothing and does not call Jev.

| Band | Context used | Message |
| --- | --- | --- |
| (none) | below 40% | No message. Jev is not called. |
| notice | 40% or more | Only if the task changes |
| recommend | 60% or more | Only if the task changes |
| request | 80% or more | Always |

- Task changes and the previous task is finished: the hook suggests `/clear` (or `/compact` to keep a summary).
- Task changes and the previous task is not finished: the hook suggests `/compact`.
- Same task, request band: the hook suggests `/compact` at the next good break.

## Install

Add to `~/.claude/settings.json` or `.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"$HOME/.claude/skills/jev-compact-advisor/scripts/compact_advisor_hook.py\"",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```

Change the path if the skill is in a different folder.

## Settings

| Variable | Default | Effect |
| --- | --- | --- |
| `JEV_COMPACT_WINDOW_TOKENS` | 200000 | Size of the context window |
| `JEV_COMPACT_BANDS` | `0.4,0.6,0.8` | Notice, recommend, and request bands |
| `JEV_COMPACT_SWITCH_AT` | 0.6 | Minimum probability for "different task" and "finished" |

## Limits

- Claude cannot run `/compact` itself. The hook advises the user only.
- The context size is an estimate: the characters of the messages after the last compaction, divided by 4. The system prompt, tools, and skills are not counted. Set `JEV_COMPACT_WINDOW_TOKENS` lower to allow for them.
- Jev sees the last 3 user prompts and the last assistant message, not the full session.
- The hook skips prompts that start with `/`.
- If Jev fails, the hook writes to stderr and the prompt continues.
