---
name: jev-review-triage
description: Run a cheap Jev first pass before a code review - Jev answers seven yes/no risk questions about the change, then small safe changes get one quick review round and risky changes get the full review. Use when the user asks to review a change, a diff, a branch, or a pull request, and before Claude starts a code review of its own work.
---

# Jev Review Triage

The agent that built a change must not be the only one to check it. A full review by a second model is slow, because it works step by step. Most small changes do not need it.

Jev does not replace the reviewer. It is a fast step before the review. Jev reads the change and answers seven yes/no questions:

| Question id | Does the change... |
| --- | --- |
| `breaks_rule` | break a project rule (`CLAUDE.md`, `AGENTS.md`, or `--rules`)? |
| `should_not_change` | edit something that must not be edited, or edit outside the task? |
| `access_control` | affect who can access what? |
| `data_shape` | alter a schema, migration, or data format? |
| `public_contract` | alter a public API, endpoint, CLI option, or exported type? |
| `security_sensitive` | touch secrets, cryptography, validation, shell, or network code? |
| `weakens_tests` | delete, skip, or weaken tests? |

- If Jev says **no** to all questions (each probability below 0.2), the mode is `light`.
- If Jev says **yes** or is **not sure** for any question, the mode is `full`.

Risky changes still get a full review. Small changes finish much faster.

Requires the `jev-setup` skill (a key in the environment).

## Procedure

1. Run the triage on the change:

   ```bash
   # uncommitted changes
   python <this-skill-dir>/scripts/triage_change.py --task "<what the change is for>"

   # a branch
   python <this-skill-dir>/scripts/triage_change.py --base main --task "<what the change is for>"
   ```

   Use `--staged` for staged changes only, or `--diff-file` for a patch file. Use `--rules` to give rule files.

2. Read the `mode` in the JSON result.

3. **`light`:** Do one quick review round. Read the diff one time. Look for clear bugs, typos, and missing error handling. Report the findings. Do not do a second round.

4. **`full`:** Do the full review as usual. Start with the items in `reasons`. Use a separate reviewer (ex. a subagent or the `/code-review` skill) if one is available. Give each flagged risk a specific check.

5. **`none`:** The diff is empty. Tell the user.

6. Tell the user the mode and the reasons in one or two lines, before the review findings.

## Example result

```json
{
  "mode": "full",
  "reasons": ["access_control: yes (p=0.94)", "weakens_tests: uncertain (p=0.31)"],
  "answers": {"breaks_rule": 0.04, "access_control": 0.94, "weakens_tests": 0.31}
}
```

## Limits

- Jev sees the first 40,000 characters of the diff. A larger diff always gets `full`.
- If Jev fails, the mode is `full`. The triage never skips a review.
- The 0.2 threshold (`--light-below`) is a first guess. Lower it to send more changes to the full review.
