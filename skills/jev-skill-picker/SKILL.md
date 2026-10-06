---
name: jev-skill-picker
description: Install a UserPromptSubmit hook in which Jev reads the name and description of each Claude Code skill plus the user prompt, then tells Claude which one skill to use, or none. Use when the user has many skills and Claude picks the wrong skill or no skill, or when the user asks to set up the Jev skill picker or faster skill selection.
---

# Jev Skill Picker

Claude Code loads the name and description of each skill into the context. Claude must then decide which skill to use. With many skills, this decision is slow and Claude can choose incorrectly.

This hook gives the decision to Jev. For each prompt, Jev reads the same names and descriptions, and picks one skill or `none`. The hook then tells Claude which skill to load. Claude does not have to compare all skills itself.

Requires the `jev-setup` skill (a key in the environment).

## Install

Add to `~/.claude/settings.json` (all projects) or `.claude/settings.json` (one project):

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"$HOME/.claude/skills/jev-skill-picker/scripts/skill_picker_hook.py\"",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```

Change the path if the skill is in a different folder.

## Test

```bash
echo '{"prompt": "turn this spec into a task list", "cwd": "."}' \
  | python <this-skill-dir>/scripts/skill_picker_hook.py --verbose
```

`--verbose` writes the pick, the confidence, and the time to stderr.

## Behavior

- The hook reads skills from `~/.claude/skills/`, `<project>/.claude/skills/`, and each folder in `JEV_SKILL_DIRS`.
- The hook skips prompts that start with `/`. A slash command already names what to run.
- The hook adds context only when Jev picks a skill with a confidence of 0.5 or more. Set `JEV_SKILL_PICKER_MIN_CONFIDENCE` to change this value.
- If Jev picks `none`, or the confidence is low, the hook adds nothing. Claude decides as usual.
- **Cascade for many skills.** If there are more than 30 skills (`JEV_SKILL_PICKER_CASCADE_AT`), the hook makes two requests. First Jev picks a category, then a skill in that category. Each question has fewer options, so the pick is faster and more accurate. The category is the `category:` field in the skill frontmatter. If there is no `category:` field, it is the name prefix before the first `-` or `:` (ex. `jev-explore` is in `jev`). Add `category:` fields when the name prefixes do not group the skills well.
- If Jev fails, the hook writes to stderr and does not stop the prompt.

## Limits

- Plugin skills are not read. Add their folders to `JEV_SKILL_DIRS` if necessary.
- In the cascade, a wrong category means a wrong skill or no skill. The hook then adds nothing, and Claude decides as usual.
- The frontmatter parser is simple. It reads single-line values and indented block values (`>` or `|`). Other YAML forms can fail.
- Jev picks one skill only. A prompt that needs two skills gets the better match.
- The pick is only as good as the skill descriptions. A clear "Use when..." sentence helps Jev and Claude.
