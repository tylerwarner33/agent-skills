---
name: jev-task-checklist
description: Install a Stop hook in which Jev checks each item of the task checklist (acceptance criteria or the todo list) against what Claude did, before Claude stops. If the evidence clearly does not show an item as done, the stop is blocked and Claude is told which items to finish. Use when the user asks to make sure Claude finishes all parts of a task, to check acceptance criteria automatically, or to set up the Jev task checklist.
---

# Jev Task Checklist

Claude sometimes stops before all parts of a task are done. This hook works like a presentation coach that ticks off talking points as they are covered. Before Claude stops, Jev asks one yes/no question for each checklist item: "Does the evidence show that this item is done?"

- If an item is clearly not done (probability below 0.3), the hook blocks the stop. Claude gets the list of items to finish.
- Uncertain items (0.3 to 0.7) are listed as a note in the block message. They do not block the stop alone.

Requires the `jev-setup` skill (a key in the environment).

## Step 1: Write the checklist

Use one of these sources. The hook uses the first one that it finds.

1. **Checklist file:** `.claude/jev-checklist.md` in the project. Each bullet or numbered line is one item. Checkbox lines (`- [ ] item`) also work.

   ```markdown
   # Acceptance criteria: export feature
   - The export button downloads a CSV file.
   - The CSV has a header row.
   - A unit test covers an empty export.
   - The README describes the export.
   ```

   The user or Claude can write this file at the start of a task. Delete or replace it when the task changes.

2. **Todo list:** If there is no checklist file, the hook uses the latest `TodoWrite` list in the session transcript.

Write each item as one result that a reviewer can see in the final message or the diff.

## Step 2: Install the hook

Add to `.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"$HOME/.claude/skills/jev-task-checklist/scripts/checklist_hook.py\"",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

Change the path if the skill is in a different folder.

## Evidence that Jev sees

- The last 3 assistant messages (up to 4,000 characters each).
- `git diff HEAD --stat`.
- The first 20,000 characters of `git diff HEAD`.

## Settings

| Variable | Default | Effect |
| --- | --- | --- |
| `JEV_CHECKLIST_NOT_DONE_BELOW` | 0.3 | An item below this blocks the stop |
| `JEV_CHECKLIST_DONE_AT` | 0.7 | An item below this is listed as uncertain |
| `JEV_CHECKLIST_MAX_BLOCKS` | 3 | Maximum blocks in one session |

## Loop protection

- If Claude is already continuing because of a stop hook (`stop_hook_active` is true), the hook does nothing.
- The hook counts its blocks per session in `.claude/jev-checklist-state.json`. After `JEV_CHECKLIST_MAX_BLOCKS` blocks, it stops blocking. Add this file to `.gitignore`.

## Limits

- Jev sees a summary of the work, not the full project. An item that is done in a file outside the diff (ex. a commit made earlier) can look not done. Commit-based work is not in `git diff HEAD`.
- Items that are not visible in text (ex. "the app feels fast") cannot be checked. Write items that a reviewer can see.
- The hook does nothing if there is no checklist file and no todo list.
- If Jev fails, the hook writes to stderr and lets Claude stop.
