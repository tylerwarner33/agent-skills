# agent-skills
Skills for AI coding agents.

## Jev skills (draft)

These skills use Jev, the TypeSafe decision model, as a fast decision maker inside Claude Code. Start with `jev-setup`: it explains what Jev is, where it fits in an agent loop, and where it does not. For the full guide (use cases, the agent loop, Claude Code support, design rules, benchmarks), read [Docs/Jev](Docs/Jev/README.md).

| Skill | Type | What it does |
| --- | --- | --- |
| [jev-setup](skills/jev-setup/SKILL.md) | Setup | API key, environment variables, the shared Jev client, and the design guide. All other skills need it. |
| [jev-eval](skills/jev-eval/SKILL.md) | Skill | Tests a Jev question on labeled cases and finds a good threshold. |
| [jev-ask](skills/jev-ask/SKILL.md) | Skill | Asks yes/no, choice, or score questions about files or command output, without reading them into context. |
| [jev-explore](skills/jev-explore/SKILL.md) | Skill | Keyword search, then Jev ranks the files 20 at a time. |
| [jev-skill-picker](skills/jev-skill-picker/SKILL.md) | UserPromptSubmit hook | Tells Claude which one skill fits the prompt, or none. Uses a category cascade for many skills. |
| [jev-compact-advisor](skills/jev-compact-advisor/SKILL.md) | UserPromptSubmit hook | Advises `/compact` or `/clear` when the context is large and the task changes. |
| [jev-fast-compaction](skills/jev-fast-compaction/SKILL.md) | Plugin guide | Replaces the compaction summary with Jev keep-or-drop decisions. |
| [jev-bash-gate](skills/jev-bash-gate/SKILL.md) | PreToolUse hook | Blocks irreversible or destructive Bash commands. Asks the user when Jev is not sure. |
| [jev-rule-enforcer](skills/jev-rule-enforcer/SKILL.md) | PreToolUse hook | Blocks an edit if Jev is at least 80% sure that it breaks a rule. Asks the user from 50%. |
| [jev-injection-screen](skills/jev-injection-screen/SKILL.md) | PostToolUse hook | Warns Claude and the user when a web or MCP result contains a prompt injection. |
| [jev-docs-checker](skills/jev-docs-checker/SKILL.md) | Skill + PostToolUse hook | Finds documented rules that have no test. |
| [jev-task-checklist](skills/jev-task-checklist/SKILL.md) | Stop hook | Stops Claude from finishing while a checklist item is clearly not done. |
| [jev-review-triage](skills/jev-review-triage/SKILL.md) | Skill | Seven yes/no risk questions select a light or a full review. |
| [jev-browser-explorer](skills/jev-browser-explorer/SKILL.md) | Skill (Playwright) | Jev picks the next click to test a flow in the browser. |
| [jev-dedupe](skills/jev-dedupe/SKILL.md) | Skill | Finds duplicate records and writes a merge plan for review. |

Sources:

- [Insane Jev Use Cases You Need To Use Right Now](https://www.youtube.com/watch?v=2nc_QMuNp18) (AI LABS)
- [Jev: 8 real use cases this fast, cheap model](https://www.youtube.com/watch?v=dAIIaepNhQM) (How I AI)
- [10 Levels of Jev For Agentic Engineers](https://www.youtube.com/watch?v=_U-O5lYhJ7Q) (IndyDevDan)
- [Using Jev In Your Agent Harness](https://www.youtube.com/watch?v=zaLQ0AnY9dI) (Sam Witteveen)
- [I Tested Jev vs 12 Local Decision Models](https://www.youtube.com/watch?v=zBw5BMrlZLo) (The AI Automators)

The scripts need Python 3.9 or later. They import `skills/jev-setup/scripts/jev_client.py`, so keep the `jev-*` folders next to each other.
