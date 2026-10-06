"""UserPromptSubmit hook: Jev picks the one skill that fits the prompt, or none.

Reads the name and description of each skill, the same data Claude Code loads.
Skill folders:
  ~/.claude/skills/*/SKILL.md
  <project>/.claude/skills/*/SKILL.md
  each folder in JEV_SKILL_DIRS (separated by os.pathsep)

With many skills, the pick is a cascade: Jev picks a category first, then a skill
in that category. The category is the `category:` frontmatter field, else the name
prefix before the first '-' or ':'.

Settings (environment variables):
  JEV_SKILL_PICKER_MIN_CONFIDENCE  default 0.5
  JEV_SKILL_PICKER_CASCADE_AT      default 30 (more skills than this use the cascade)

Test without Claude Code:
  echo '{"prompt": "make a slide deck", "cwd": "."}' | python skill_picker_hook.py --verbose
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "jev-setup" / "scripts"))
from jev_client import JevError, ask, choice  # noqa: E402

NONE_OPTION = "none"
MAX_OPTIONS = 254  # 255 Jev options minus the "none" option
FIELD = re.compile(r"^(name|description|category):\s*(.*)$")


def parse_frontmatter(text: str) -> dict[str, str]:
    """Read `name:` and `description:` from YAML frontmatter.

    Supports a single-line value and a block value (`>` or `|`) on indented lines.
    """
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    fields: dict[str, str] = {}
    current = None
    for line in text[3:end].splitlines():
        match = FIELD.match(line)
        if match:
            value = match.group(2).strip()
            current = match.group(1)
            fields[current] = "" if value in (">", "|", ">-", "|-") else value.strip("\"'")
        elif current and line[:1] in (" ", "\t") and line.strip():
            fields[current] = f"{fields[current]} {line.strip()}".strip()
        else:
            current = None
    return fields


def skill_dirs(project: Path) -> list[Path]:
    dirs = [Path.home() / ".claude" / "skills", project / ".claude" / "skills"]
    extra = os.environ.get("JEV_SKILL_DIRS", "")
    dirs.extend(Path(d) for d in extra.split(os.pathsep) if d)
    return dirs


def load_skills(project: Path) -> dict[str, str]:
    skills: dict[str, str] = {}
    for folder in skill_dirs(project):
        if not folder.is_dir():
            continue
        for skill_file in sorted(folder.glob("*/SKILL.md")):
            fields = parse_frontmatter(skill_file.read_text(encoding="utf-8", errors="replace"))
            name = fields.get("name") or skill_file.parent.name
            description = fields.get("description")
            if description and name != NONE_OPTION and name not in skills:
                skills[name] = {"description": description, "category": fields.get("category") or category_of(name)}
    return skills


def category_of(name: str) -> str:
    """Default category: the name prefix before the first '-' or ':', ex. jev-explore -> jev."""
    prefix = re.split(r"[-:]", name, maxsplit=1)[0]
    return prefix if prefix and prefix != name else "general"


def pick(prompt: str, options: dict[str, str], instructions: str) -> tuple[str, float]:
    options = dict(options)
    options[NONE_OPTION] = "Nothing fits. The request is general work that needs no special skill."
    answer = ask({"prompt": prompt}, {"pick": choice(instructions, options)}, timeout=10)["pick"]
    return answer.get("choice"), answer.get("confidence", 0.0)


def main() -> int:
    verbose = "--verbose" in sys.argv
    event = json.load(sys.stdin)
    prompt = (event.get("prompt") or "").strip()
    if not prompt or prompt.startswith("/"):
        return 0  # Slash commands already name what to run.

    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or ".")
    skills = load_skills(project)
    if not skills:
        return 0

    minimum = float(os.environ.get("JEV_SKILL_PICKER_MIN_CONFIDENCE", "0.5"))
    cascade_at = int(os.environ.get("JEV_SKILL_PICKER_CASCADE_AT", "30"))
    categories: dict[str, list[str]] = {}
    for name, skill in skills.items():
        categories.setdefault(skill["category"], []).append(name)

    started = time.perf_counter()
    try:
        candidates = skills
        if len(skills) > cascade_at and len(categories) > 1:
            # Step 1 of the cascade: pick a category from short summaries of its skills.
            summaries = {cat: "Skills: " + "; ".join(f"{n}: {skills[n]['description'][:90]}" for n in names)[:900]
                         for cat, names in categories.items()}
            category, category_confidence = pick(
                prompt, dict(list(summaries.items())[:MAX_OPTIONS]),
                "Which group of skills does the user request in `prompt` need? Pick none if no group clearly fits.",
            )
            if verbose:
                print(f"category={category} confidence={category_confidence:.2f}", file=sys.stderr)
            if category not in categories or category_confidence < minimum:
                return 0
            candidates = {n: skills[n] for n in categories[category]}

        if len(candidates) > MAX_OPTIONS:
            print(f"jev-skill-picker: {len(candidates)} skills, only the first {MAX_OPTIONS} are used.", file=sys.stderr)
            candidates = dict(list(candidates.items())[:MAX_OPTIONS])
        picked, confidence = pick(
            prompt, {n: s["description"] for n, s in candidates.items()},
            "Which one skill does the user request in `prompt` need? Compare the request to what "
            "each skill is for. Pick none if no skill clearly fits.",
        )
    except JevError as error:
        print(f"jev-skill-picker skipped: {error}", file=sys.stderr)
        return 0
    elapsed = time.perf_counter() - started

    if verbose:
        print(f"picked={picked} confidence={confidence:.2f} in {elapsed:.2f}s", file=sys.stderr)
    if picked == NONE_OPTION or picked not in skills or confidence < minimum:
        return 0

    context = (
        f"Jev skill picker: the `{picked}` skill fits this request (confidence {confidence:.2f}). "
        f"Load the `{picked}` skill before you start, unless the request clearly needs a different one."
    )
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
