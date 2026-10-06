---
name: jev-rule-enforcer
description: Install a PreToolUse hook that sends each edit, plus the project rules for that file, to Jev. If Jev is at least 80% sure that the edit breaks a rule, the edit is blocked before the file changes, and Claude is told which rule it broke. Use when the user asks to enforce project rules or specs, to stop Claude from breaking rules in CLAUDE.md or other rule files, or to set up the Jev rule enforcer.
---

# Jev Rule Enforcer

Rules in `CLAUDE.md` are only instructions. The model follows them most of the time, but not each time. A hook runs each time, and the model cannot skip it.

This hook runs before each `Edit`, `Write`, or `MultiEdit`. It finds the rules for the file and asks Jev one yes/no question per rule: "Does this change break the rule?" If Jev is at least 80% sure that a rule is broken, the hook blocks the edit. Claude gets the names of the broken rules, so it can fix the edit.

Example from the video: Claude was asked to create a file that reads employee data directly in the browser. This broke a project rule. The edit was blocked before the file was created, and Claude told the user which rule it broke.

Requires the `jev-setup` skill (a key in the environment).

## Step 1: Write the rules

Create `.claude/jev-rules.json` in the project. Map file patterns to rules. Give the rules inline, or in a Markdown file in which each bullet line is one rule.

```json
{
  "threshold": 0.8,
  "failClosed": false,
  "rules": [
    {
      "paths": ["src/client/**", "src/components/**"],
      "rules": [
        "Never read employee data directly in the browser. Get it through the server API.",
        "Do not store tokens in localStorage."
      ]
    },
    {
      "paths": ["src/api/**"],
      "rulesFile": "docs/rules/api.md"
    }
  ]
}
```

Write each rule as one clear sentence that a reviewer can check against a single change. Rules about the full system (ex. "the app must be fast") do not work well.

## Step 2: Install the hook

Add to `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python \"$HOME/.claude/skills/jev-rule-enforcer/scripts/rule_enforcer_hook.py\"",
            "timeout": 20
          }
        ]
      }
    ]
  }
}
```

Change the path if the skill is in a different folder.

## Step 3: Test

Ask Claude to make a change that clearly breaks one rule. The edit must be blocked, and the message must name the rule. Then ask for a change that follows the rules. The edit must continue.

You can also test without Claude Code:

```bash
echo '{"tool_name":"Write","tool_input":{"file_path":"src/client/employees.ts","content":"const data = JSON.parse(localStorage.employees)"},"cwd":"."}' \
  | python <this-skill-dir>/scripts/rule_enforcer_hook.py
```

## Settings

| Setting | Default | Effect |
| --- | --- | --- |
| `threshold` | 0.8 | Minimum Jev probability that a rule is broken, to block the edit |
| `askAt` | 0.5 | From this value up to `threshold`, Jev is not sure. Claude Code asks the user to approve the edit. Set it equal to `threshold` to turn this off. |
| `failClosed` | `false` | If `true`, block the edit when Jev cannot be reached |

A wrong block costs more than a question to the user. The `askAt` band sends the uncertain cases to a person.

## Behavior

- Files with no matching rules are not sent to Jev.
- Files outside the project are not checked.
- If Jev fails and `failClosed` is `false`, the hook writes to stderr and the edit continues.
- For `Edit` and `MultiEdit`, Jev sees the old and the new text only, not the full file. A rule that needs the full file can be missed.
- If a rule blocks correct edits, make the rule more specific or raise `threshold`. Do not remove the hook.
