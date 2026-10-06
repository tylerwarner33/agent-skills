---
name: jev-ask
description: Ask Jev fast, cheap yes/no, choice, or score questions about files, globs, or command output, without reading them into Claude's context. Use to screen many files with the same question (ex. which files touch auth, contain a TODO, or relate to a bug), to classify test or build output, or to check an assumption or a fix before acting. Use when only an answer about the content is needed, not the content itself.
---

# Jev Ask

Claude often reads a file only to answer a question about it: "Does this file validate tokens?" "Which layer is it?" "Is it related to this bug?" Each read fills the context and costs time. If Claude needs an answer and not the content, Jev can answer instead. Jev reads the file, and Claude gets only the answer.

This is IndyDevDan's levels 8 to 10:

- **Level 8:** one question about one file, without a read.
- **Level 9:** the same questions about many files, in parallel.
- **Level 10:** Claude decides when to ask Jev, ex. to classify a test failure, or to check a fix.

Requires the `jev-setup` skill (a key in the environment).

## When to use

- Screen a set of files: "Which of these 60 files can be related to the rounding bug?" Then read only the files with a high probability.
- Classify each file in a set: layer, owner, kind of change.
- Classify command output: test failures, build errors, log lines.
- Check an assumption before acting: "Is this a simple rounding fix?" "Does this file still contain the bug?"

Do not use it when Claude must edit the file, or when the answer needs reasoning across several files. Read the file in those cases.

## Commands

Yes/no questions over a glob, filtered to likely matches:

```bash
python <this-skill-dir>/scripts/ask_jev.py --files "src/**/*.ts" \
  --yes-no "Is this file relevant to a bug in which prorated amounts are rounded incorrectly?" \
  --min 0.5
```

Two questions per file, in one request per file:

```bash
python <this-skill-dir>/scripts/ask_jev.py --files src/auth/*.ts src/routes/*.ts \
  --yes-no "Does this file touch authentication or authorization?" \
  --choice "Which layer is this file?" \
  --options http="HTTP handler" domain="Domain logic" data="Data access" other="None of these"
```

Classify command output:

```bash
npm test 2>&1 | python <this-skill-dir>/scripts/ask_jev.py --stdin \
  --choice "What kind of failure does this test output show?" \
  --options bug="A real bug in the code" flaky="A flaky or timing test" env="A setup or environment problem" none="All tests pass"
```

A score:

```bash
python <this-skill-dir>/scripts/ask_jev.py --files src/billing/*.ts \
  --score "How risky is this file to change?" \
  --levels "Trivial: no logic" "Low: simple logic with tests" "Medium: shared logic" "High: money, auth, or data loss"
```

Use `--json` for a machine-readable result.

## How to write good questions

- Ask about one thing. Split "Is it a bug and is it urgent?" into two questions.
- Put the full meaning in the question. Jev does not see the conversation.
- For `--choice`, add a `none` option when no option may fit.
- If an answer is near 0.5, Jev is not sure. Read the file, or ask a narrower question.
- If one pass is not good enough, add a second pass: screen with a yes/no, then ask a more specific question about the files that pass.

## Safety and limits

- File content is sent to the Jev API. Files that look like secrets (`.env`, `*.pem`, `*.key`, `*credentials*`, and similar) are skipped unless you add `--allow-secrets`. Do not add it without the user's approval.
- Each file is cut at 24,000 characters (`--max-chars`). Long inputs lower Jev's accuracy. The output marks cut files with `[truncated]`.
- Folders such as `node_modules`, `.git`, `bin`, and `obj` are skipped.
- Jev's answer is a filter, not proof. Before Claude reports a finding, read the files that matter.
