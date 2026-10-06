---
name: jev-eval
description: Test one Jev question against a set of labeled cases before you trust it - reports accuracy, a threshold table with precision and recall, a majority-label baseline that shows class imbalance, latency, and the worst misses. Use before shipping any Jev hook, gate, or threshold (ex. in jev-rule-enforcer or jev-review-triage), when the user asks how accurate a Jev question is, or when a Jev decision gives wrong results.
---

# Jev Eval

The thresholds in the `jev-*` skills are first guesses. A threshold is only correct for your data. Benchmarks show that Jev is accurate on many tasks, but the result changes much from one data set to another. The only benchmark that matters is your own cases.

This skill runs one question against labeled cases and tells you:

- The accuracy, and for a yes/no (`noul`) question, the precision and recall at each threshold from 0.1 to 0.9.
- A **baseline** that always gives the most common label. In one benchmark, a baseline that always said "not relevant" got 90.6% accuracy, because most documents were not relevant. If Jev is not much better than the baseline, the question is not useful yet.
- The latency (p50 and p95).
- The worst misses, so you can fix the question.

Requires the `jev-setup` skill (a key in the environment).

## Step 1: Write the question

Put one question object in a JSON file. Use the same question as the hook or script will use.

```json
{
  "type": "noul",
  "instructions": "Is the shell command in `command` irreversible? It is irreversible if nothing can restore what it deletes or overwrites.",
  "criteria": {"true": "The command cannot be undone.", "false": "The command is read-only or can be undone."}
}
```

## Step 2: Make labeled cases

Write 20 to 100 cases in a JSONL file. One case per line.

```json
{"state": {"command": "git push --force origin main"}, "label": true}
{"state": {"command": "ls -la src"}, "label": false}
```

| Question type | Label |
| --- | --- |
| `noul` | `true` or `false` |
| `choice` | The correct option name |
| `score` | The correct level index (0, 1, 2, ...) |

Rules for good cases:

- Use real inputs from the project, not only easy examples.
- Include hard cases near the boundary (ex. `rm -rf node_modules` is reversible, `find . -delete` is not).
- Include enough cases of the rare label. If only 5% of cases are "yes", add more "yes" cases or read the recall carefully.
- Ask the user to check the labels. A wrong label makes a wrong result.

## Step 3: Run

```bash
python <this-skill-dir>/scripts/eval_question.py --question question.json --cases cases.jsonl
```

Add `--threshold 0.8` to see the details at one threshold, and `--json` for a machine-readable result.

## Step 4: Read the result

- **Accuracy vs baseline:** Jev must be clearly better than the baseline.
- **Threshold table (`noul`):** Select the threshold from the cost of each mistake, not only from accuracy.
  - A gate that blocks dangerous actions needs high **recall** (few dangerous actions get through).
  - A gate that blocks normal work when it is wrong needs high **precision** (few false blocks).
- **By confidence (`choice`):** If accuracy is low below a confidence value, send those cases to Claude or to the user.
- **Worst misses:** Read each one. Decide if the label is wrong, the question is not clear, or the state does not have the necessary information.

## How to improve a weak question

- Make the instructions and the criteria more specific. Define the boundary with examples.
- Try a different question type. A yes/no question can work better as a `choice` or a `score`, and the reverse.
- Add a second pass. Ex. ask a broad question first, then a narrow question for the cases that pass.
- Make the state shorter. Long inputs reduce accuracy and increase latency. Send only the relevant part (ex. the retrieved section of a handbook, not the full handbook).
- Ask one judgment per question. Compound questions ("is it A and also B?") work less well.

## Other decision models

Open decision models (ex. Winnow, Decider, Laya) can run locally. Point `JEV_URL` and `JEV_MODEL` at a compatible server and run the same eval to compare. Check these limits first:

- Some models accept only 16 options in a `choice`. Requests with more options fail.
- Some models accept only short inputs (ex. 8K tokens).
- A local model is fast with short inputs, but it can be much slower than hosted Jev with long inputs (ex. a 20,000-token handbook).
