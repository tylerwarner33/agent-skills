# What Jev Is

Jev is a decision model. An LLM writes its answer one token at a time. Jev answers all questions at the same time and returns numbers.

- Sam Witteveen calls it a "smart if statement".
- IndyDevDan calls it "intelligent question answering that is programmable through JSON".
- John Lindquist describes it as unstructured input in, structured data out.

## Jev against an LLM

| | LLM (System 2) | Jev (System 1) |
| --- | --- | --- |
| Output | Free text, code, tool calls | A probability, a pick from your options, or a score on your scale |
| Speed | Seconds, longer with reasoning | Usually less than one second |
| Cost | Input and output tokens | Input tokens only. The answer is free. |
| Confidence | Not given | Given with each answer |
| Tools and code | Yes | No. Jev cannot write code or call tools. |
| Best for | Open tasks, writing, multi-step reasoning | Narrow decisions from a known set of answers |

Rule of thumb from TypeSafe: if a panel of smart people can answer the question in a few seconds, use Jev. If they must go away and write an answer, use an LLM.

## The three question types

Each request has one `state` and one or more named questions. All questions see the same state and run in parallel. They cannot see each other's answers.

| Type | Question | Returns | Notes |
| --- | --- | --- | --- |
| `noul` | Is it true? | The probability of yes | Use one per label when several labels can apply. A value near 0.5 means "not sure", not "a medium amount". |
| `choice` | Which one? | The pick, the probability of each option, a confidence | Up to 255 options. Add a "none" option when nothing may fit. |
| `score` | How much? | A probability-weighted score, the level distribution, a confidence | 2 to 10 levels that you describe. Each level must stand on its own. |

Through the Vercel AI SDK, the yes/no type is named `boolean`. On the HTTP APIs it is `noul`.

```
noul      P(yes) ██████████████████▋  0.93

choice    bug      █████████████████▌   0.88
          feature  █▊                   0.09
          question ▌                    0.03

score     0 none   ▊                    0.04
          1 some   █████▊               0.29
          2 high   █████████████▍       0.67
```

## Request

```jsonc
// POST https://ai-gateway.vercel.sh/typesafe/v1/systemone  (or https://api.typesafe.ai/v1/systemone)
// Authorization: Bearer $AI_GATEWAY_API_KEY
{
  "model": "typesafe-ai/jev",            // "jev-latest" on the TypeSafe API
  "state": { "ticket": "Export button crashes the settings page in Safari. Works in Chrome." },
  "questions": {
    "is_bug":   { "type": "noul",   "instructions": "Does `ticket` report a defect?" },
    "priority": { "type": "choice", "instructions": "How urgent is `ticket`?",
                  "criteria": { "high": "Blocked, losing money, or angry customers",
                                "normal": "A workaround exists", "low": "Cosmetic" } },
    "impact":   { "type": "score",  "instructions": "How many users does `ticket` affect?",
                  "criteria": ["One user", "Some users", "All users"] }
  }
}
```

## Response

```jsonc
{
  "answers": {
    "is_bug":   { "type": "noul", "noul": 0.97 },
    "priority": { "type": "choice", "choice": "normal", "confidence": 0.81,
                  "probabilities": { "high": 0.14, "normal": 0.83, "low": 0.03 } },
    "impact":   { "type": "score", "score": 1.2, "confidence": 0.62,
                  "probabilities": { "0": 0.08, "1": 0.64, "2": 0.28 } }
  },
  "usage": { "input_tokens": 312, "output_tokens": 20 }
}
// The values are examples. The shape is from the TypeSafe and Vercel API docs.
```

## Python, with the client in this repo

`skills/jev-setup/scripts/jev_client.py` uses only the Python standard library.

```python
from jev_client import ask, noul, choice

answers = ask(
    state={"command": "git push --force origin main"},
    questions={
        "destructive": noul("Does `command` destroy history or data that matters?"),
        "reversibility": choice("How reversible is `command`?",
            {"read_only": "Only reads", "reversible": "Easy to undo", "irreversible": "Cannot come back"}),
    },
)
if answers["destructive"]["noul"] >= 0.8:
    block("irreversible command")
```

## Rules for good questions

- Put the facts in `state`. Use named JSON fields when the data has several parts. Refer to a field with a backticked path, ex. `files[3].excerpt`.
- Put the judgment in `instructions`, and define the answers in `criteria`.
- The question id is not sent to the model. Put the full meaning in the question text.
- Ask one narrow judgment per question. Split compound questions.
- Questions in one request cannot see each other. If a question needs an earlier answer, send a second request.
