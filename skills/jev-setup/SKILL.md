---
name: jev-setup
description: Set up access to Jev, the TypeSafe decision model, for Claude Code - get an API key from Vercel AI Gateway or TypeSafe, save it as an environment variable, and test the connection. Also holds the shared Jev client that the other jev-* skills use. Use when the user asks to set up, connect, configure, or test Jev, or when another jev-* skill reports that Jev is not configured.
---

# Jev Setup

Jev is a decision model from TypeSafe. It does not write text. It picks from options that you give it, and it returns a probability or a confidence value with each pick. One request is fast (a fraction of a second) and you pay only for the input tokens.

Jev cannot write code or use tools. In Claude Code, it is a fast **decision maker**. Claude stays the main model.

The other `jev-*` skills in this folder import `scripts/jev_client.py` from this skill. Keep this skill installed next to them.

## Step 1: Get a key

New signups on the TypeSafe platform can be paused. Jev is also available through Vercel AI Gateway and OpenRouter. The client in this skill supports Vercel AI Gateway and the TypeSafe API.

**Vercel AI Gateway (recommended):**

1. Open the Vercel dashboard. Go to **AI Gateway** > **API Keys**.
2. Create a key. Copy it immediately. Vercel shows the key one time only.

**TypeSafe API:** Create a key on the TypeSafe platform.

Do not paste the key into chat. The user must set it.

## Step 2: Save the key as an environment variable

Tell the user to set the key in the terminal before they start Claude Code. Claude Code and its hooks can then read it.

```bash
# Vercel AI Gateway
export AI_GATEWAY_API_KEY="<key>"

# or TypeSafe
export TYPESAFE_API_KEY="<key>"
```

To keep the key for each session, the user can add it to the `env` block of `~/.claude/settings.json` (not a project settings file that goes into git).

The client selects the endpoint from the key that is set:

| Key that is set | Endpoint | Model id |
| --- | --- | --- |
| `AI_GATEWAY_API_KEY` | `https://ai-gateway.vercel.sh/typesafe/v1/systemone` | `typesafe-ai/jev` |
| `TYPESAFE_API_KEY` | `https://api.typesafe.ai/v1/systemone` | `jev-latest` |

Use `JEV_URL` and `JEV_MODEL` to override the endpoint or the model (ex. for OpenRouter).

## Step 3: Test the connection

```bash
python <this-skill-dir>/scripts/jev_client.py
```

A good result shows `OK`, the endpoint, the time, and a `noul` answer near 1.0.

## Jev question types

| Type | Use it for | Answer |
| --- | --- | --- |
| `noul` | Is a condition true? | `noul`: probability of yes (0 to 1) |
| `choice` | Pick one option from a set (max 255) | `choice`, `probabilities`, `confidence` |
| `score` | Rate on 2 to 10 ordered levels | `score`, `probabilities`, `confidence` |

Rules for good questions:

- Put the data in `state`. Use named JSON fields when the data has several parts. Refer to a field in the question with a backticked path, ex. `files[3].excerpt`.
- Ask one narrow judgment per question. Put the full meaning in the question text. The question id is not sent to the model.
- Questions in one request run in parallel and cannot see each other. Put independent questions in one request.
- Add a "none" option to a `choice` when no option can fit.
- A `noul` near 0.5 means "not sure". It does not mean "a medium amount".
- Test the thresholds on real cases. The thresholds in these skills are first guesses.

## Where Jev fits in an agent loop

Most model calls in an agent loop do not write anything. They make decisions. Hook a Jev decision at one of these four points (Sam Witteveen):

| Point in the loop | Decision | Skills in this folder |
| --- | --- | --- |
| Before the prompt is built | Which skills or tools to load | `jev-skill-picker` |
| Before the model call | Which model or agent to use; should the context be compacted | `jev-compact-advisor`. For subagent models, a `PreToolUse` hook on the `Agent` tool can set `model` with `updatedInput`. |
| Before a tool runs | Is it safe; does it break a rule | `jev-bash-gate`, `jev-rule-enforcer` |
| After a result comes back | Is it good enough, relevant, or safe to trust | `jev-injection-screen`, `jev-explore`, `jev-ask`, `jev-task-checklist` |

In Claude Code, points 3 and 4 work fully. Points 1 and 2 work in part: a hook can recommend a skill but cannot unload one, and a hook can set a subagent model but cannot switch the main model. See `Docs/Jev/04-claude-code-support.md` and `Docs/Jev/09-model-routing.md` in this repo.

Rule of thumb (from TypeSafe): if a panel of smart people can answer the question in a few seconds, use Jev. If they must think and write an answer, use an LLM.

## Where Jev does not fit

- Anything that needs text back, multi-step reasoning, or facts joined from several sources.
- Very long state. Accuracy drops on long inputs. Split the state, or retrieve only the relevant part first.
- Images (Jev is text only).
- Compound questions. Split them into separate questions.
- Text that can contain prompt injection. Jev can also be injected. Ask an injection question first (see `jev-injection-screen`), or keep untrusted text out of decisions that act.

## Tune the decisions

- **Thresholds are policy.** Keep raw probabilities. Set thresholds in code or config. Test them with `jev-eval` on labeled cases before you trust them.
- **Use bands, not one line.** Act when Jev is sure. Ask a person or a stronger model when Jev is not sure. A wrong action costs more than a question.
- **Escalate uncertain answers.** Through Vercel AI Gateway, `gateway_fallback(model, question, confidence_below)` reruns a request on a stronger model when a Choice or Score confidence is low:

  ```python
  from jev_client import ask, choice, gateway_fallback
  answers = ask(state, {"intent": choice(...)}, extra=gateway_fallback("anthropic/claude-sonnet-5-5", "intent", 0.6))
  ```

  Check the model id in the gateway catalog. Both stages are billed.
- **Add a second pass.** If one pass is not accurate enough, screen with a broad question, then ask a narrower question about the items that pass. Later you can merge the passes when the data shows the pattern.
- **Try another question type.** A question that does not work as a yes/no can work as a choice or a score.
- **Score in parts, weight in code.** For a composite score (ex. ticket priority, review risk), ask one Score per dimension. Combine them with weights in code. Then you tune a number, not a prompt.

## Hosted Jev or a local decision model

The Jev API is hosted. The state that you send leaves your machine. Open decision models (ex. Winnow 12B, Decider 4B, Laya) run on your own hardware. In The AI Automators benchmark of more than 7,000 decisions:

- Jev had the best total accuracy (95.2%). Winnow 12B (94.6%) and Decider 4B (94.5%) were close. A small model won some categories.
- With short inputs, the local models were faster (about 50 ms against 245 ms). With a 20,000-token input, hosted Jev was much faster.
- Some models accept only 16 options or 8K tokens of input. Check the limits before you choose.

If a local server accepts the same request shape, point `JEV_URL` and `JEV_MODEL` at it. Test it with `jev-eval` first.

## Use the client in a script

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "jev-setup" / "scripts"))
from jev_client import JevError, ask, choice, noul, score

answers = ask(
    state={"ticket": "I was charged twice."},
    questions={"refund": noul("Does `ticket` ask for money back?")},
)
print(answers["refund"]["noul"])
```

## Rules for hooks that call Jev

- **Fail open.** If Jev is not configured or a request fails, write a short message to stderr and exit 0. Do not block Claude.
- Keep a short timeout (ex. 10 to 20 seconds). A hook runs on each matching event.
- Never print the API key.

## Sources

- Video: "Insane Jev Use Cases You Need To Use Right Now" (AI LABS, 2026-09-28).
- Video: "Jev: 8 real use cases this fast, cheap model" (How I AI, John Lindquist, 2026-09-30).
- Video: "10 Levels of Jev For Agentic Engineers" (IndyDevDan).
- Video: "Using Jev In Your Agent Harness" (Sam Witteveen).
- Video: "I Tested Jev vs 12 Local Decision Models" (The AI Automators, 2026-09-28).
- TypeSafe HTTP API: https://docs.typesafe.ai/api.md
- Vercel AI Gateway TypeSafe API: https://vercel.com/docs/ai-gateway/sdks-and-apis/typesafe
