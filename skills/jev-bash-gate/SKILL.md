---
name: jev-bash-gate
description: Install a PreToolUse hook that sends each Bash command to Jev before it runs. Jev rates the command as read-only, reversible, or irreversible, and checks for destructive intent and data sent out. Irreversible or destructive commands are blocked, uncertain ones ask the user. Use when the user asks to make the Bash tool safer, block dangerous or destructive commands, stop force pushes or rm -rf, or guard an agent that runs without supervision.
---

# Jev Bash Gate

The Bash tool is the most dangerous tool an agent has. A list of blocked commands is never complete: there are many ways to delete files (ex. `find -delete`) and many commands that you do not know. Jev understands what a command does, so it can catch variants that a pattern list misses.

For each Bash command, this hook asks Jev three questions in one request:

| Question | Type | Answer |
| --- | --- | --- |
| How reversible is the command? | choice | `read_only`, `reversible`, or `irreversible` |
| Does it intend to destroy data, history, or state? | noul | probability |
| Does it send local data or secrets out? | noul | probability |

Then the hook applies the policy:

| Highest risk probability | Result |
| --- | --- |
| 0.8 or more (`denyAt`) | The command is blocked. Claude gets the reason. |
| 0.5 or more (`askAt`) | Claude Code asks the user to approve. |
| Less than 0.5 | No decision. The normal permission rules apply. |

The hook never approves a command by itself. It can only block a command or send it to the user.

Requires the `jev-setup` skill (a key in the environment).

## Install

Add to `~/.claude/settings.json` (all projects) or `.claude/settings.json` (one project):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python \"$HOME/.claude/skills/jev-bash-gate/scripts/bash_gate_hook.py\"",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```

Change the path if the skill is in a different folder.

## Configure (optional)

Create `.claude/jev-bash-gate.json` in the project:

```json
{
  "denyAt": 0.8,
  "askAt": 0.5,
  "skipPatterns": ["^(ls|pwd|cat)(\\s|$)", "^git (status|diff|log)(\\s|$)", "^npm test$"],
  "notes": "The dist/ and .cache/ folders are build output. The data/ folder holds user data and has no backup."
}
```

- `skipPatterns`: regular expressions for plain read-only commands. These commands skip the Jev call, to save time. A command with a pipe, redirect, `;`, `&&`, or `$(...)` never skips.
- `notes`: project facts that change the risk, ex. which folders are safe to delete. Jev reads them with each command.

## Test

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"git push --force origin main"},"cwd":"."}' \
  | python <this-skill-dir>/scripts/bash_gate_hook.py
```

The result must be a `deny`. Then test a safe command, ex. `npm test`. It must give no output.

## Limits

- If Jev fails, the hook does nothing and the normal permission rules apply.
- Jev sees the command text, not the files. `rm -rf build` is safe in one project and a disaster in another. Use `notes` to give this context.
- The thresholds are first guesses. Use the `jev-eval` skill with real commands from your sessions to tune them.
- This hook adds a gate. It does not replace sandboxing or the Claude Code permission rules.

## Source

IndyDevDan, "10 Levels of Jev For Agentic Engineers", levels 4 (confidence gating) and 6 (in-agent guardrail hooks).
