# Jev Guide

Jev is the first "System One" decision model from TypeSafe. You give it some state and typed questions. It does not write text. It returns typed answers with probabilities, fast and at a very low cost. An LLM still does the work that needs writing and reasoning. Jev makes the small decisions around that work.

This guide comes from five videos and the TypeSafe and Vercel API docs. It also records what Claude Code can and cannot do with Jev, and how the `jev-*` skills in this repo connect to it.

## Read in this order

| # | Page | What it explains |
| --- | --- | --- |
| 1 | [What Jev is](01-what-is-jev.md) | Jev against an LLM, the three question types, request and response shapes |
| 2 | [Use cases and limits](02-use-cases.md) | What Jev is good for, and where you must use an LLM |
| 3 | [Jev in an agent loop](03-agent-loop.md) | The four decision points, and the three ways to insert Jev: hooks, skills, your own harness |
| 4 | [Claude Code support](04-claude-code-support.md) | Which decision points Claude Code supports natively, and the workarounds for model routing |
| 5 | [Connect Jev](05-connect.md) | Keys, endpoints, and how to plug Jev into Claude Code, a harness, or a framework |
| 6 | [Design rules](06-design-rules.md) | Thresholds, bands, question design, escalation, testing |
| 7 | [Speed, cost, and local models](07-performance-and-local.md) | Figures from the videos, the benchmark, hosted against local |
| 8 | [The skill kit](08-skill-kit.md) | The 15 `jev-*` skills in this repo, and how each one is inserted |
| 9 | [Model routing in Claude Code](09-model-routing.md) | Every native way to choose the model, a tested hook that changes the subagent model, and where Jev decides |

## Jev in one picture

```
            ┌──────────────────────────────┐
  state ───►│                              │──► noul:   P(yes) = 0.93
            │   Jev (System One model)     │──► choice: "bug" (conf 0.88)
questions ─►│   all questions in parallel  │──► score:  1.7 of 0..2 (conf 0.62)
            └──────────────────────────────┘
               < 1 s, input tokens only
```

## Sources

- [Insane Jev Use Cases You Need To Use Right Now](https://www.youtube.com/watch?v=2nc_QMuNp18) (AI LABS): seven Claude Code use cases.
- [Jev: 8 real use cases this fast, cheap model](https://www.youtube.com/watch?v=dAIIaepNhQM) (How I AI, with John Lindquist): app and data use cases.
- [10 Levels of Jev For Agentic Engineers](https://www.youtube.com/watch?v=_U-O5lYhJ7Q) (IndyDevDan): from a "smart if statement" to an agent tool.
- [Using Jev In Your Agent Harness](https://www.youtube.com/watch?v=zaLQ0AnY9dI) (Sam Witteveen): hook points and limits.
- [I Tested Jev vs 12 Local Decision Models](https://www.youtube.com/watch?v=zBw5BMrlZLo) (The AI Automators): accuracy and latency benchmark.
- [TypeSafe HTTP API](https://docs.typesafe.ai/api.md) and the [TypeSafe docs index](https://docs.typesafe.ai/llms.txt).
- [Vercel AI Gateway TypeSafe API](https://vercel.com/docs/ai-gateway/sdks-and-apis/typesafe).

Compiled in October 2026. The figures and claims from the videos are not checked. Prices and APIs change.
