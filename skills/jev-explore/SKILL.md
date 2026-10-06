---
name: jev-explore
description: Find the files in a codebase that answer a question, fast and cheap - a keyword search finds candidate files, then Jev scores them 20 at a time so Claude opens only the top few. Use instead of the Explore agent when the user asks where something is, which file handles something, or to find code related to a feature, and the search is in one repository.
---

# Jev Explore

The Explore agent now uses the same model as the main session. With a large model, each search is slow and expensive. This skill does the same job with a keyword search and Jev:

1. A keyword search finds the files that can be related to the question.
2. Jev scores those files, 20 at a time in parallel, on how closely each file matches the question.
3. Claude opens only the top few files.

In the video, Jev ranked 35 files in 1.6 seconds and put the correct file first.

Requires the `jev-setup` skill (a key in the environment). Uses `rg` (ripgrep) if it is installed, else a slower Python scan.

## Procedure

1. Write the question in plain words, ex. "where is the session timeout set".
2. Select 2 to 6 keywords. Include names that can be in the code: identifiers, config keys, route paths, and synonyms (ex. `timeout`, `expire`, `ttl`, `session`).
3. Run:

   ```bash
   python <this-skill-dir>/scripts/rank_files.py \
     --query "where is the session timeout set" \
     --keywords session timeout expire ttl \
     --root .
   ```

4. Read the top files only, in order. Stop when you have the answer.
5. If no top file has a score of 3 or more, run the search again with different keywords. Then use the Explore agent or Grep if it still fails.

## Output

```
Ranked 35 files in 1.62s (search 0.08s). Keywords: session, timeout, expire, ttl
4.00  (conf 0.91)  src/auth/session.ts
3.10  (conf 0.64)  src/config/defaults.ts
...
```

The score is from 0 to 4:

| Score | Meaning |
| --- | --- |
| 0 | Not related |
| 1 | Mentions a related term only |
| 2 | Uses the thing, but does not define or handle it |
| 3 | Contains a main part of the answer |
| 4 | The exact file |

Use `--json` for a machine-readable result, and `--top N` for more or fewer files.

## Limits

- Jev sees the path, the first 8 lines, and up to 15 matching lines of each file. It does not see the full file.
- If the keyword search does not find the correct file, Jev cannot rank it. Good keywords are important.
- The script searches at most 100 candidate files (`--max-candidates`). These are the files with the most keyword matches.

## Option: replace Explore for one project

To make Claude use this skill instead of Explore in one project, add this line to the project `CLAUDE.md`:

```markdown
To find files, use the jev-explore skill first. Use the Explore agent only if jev-explore finds no file with a score of 3 or more.
```
