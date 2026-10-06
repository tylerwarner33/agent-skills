---
name: jev-docs-checker
description: Use Jev as an independent judge that finds which rules in the project docs have no test - ex. access rules for who can see or change what. Runs on demand, or as a hook after Claude edits access-control files. Claude then writes the missing tests from the Jev report. Use when the user asks to check whether docs, specs, or rules are covered by tests, to find untested rules, or to check a part of the app against its docs.
---

# Jev Docs Checker

A project has many docs that describe the features and rules. The agent can lose track of them. The model that built a feature must not also judge it. Jev is fast and cheap, so it can be the judge each time.

For each rule in a rules doc, Jev answers one yes/no question: "Does a test check this rule?" The result shows which rules are covered, missing, or uncertain.

Requires the `jev-setup` skill (a key in the environment).

## Prepare the rules doc

Write each rule as one bullet or numbered line. Other lines are ignored.

```markdown
# Access rules
- An employee can see only their own timesheets.
- A manager can see the timesheets of their direct reports only.
- Only an admin can change a user role.
```

## Run on demand

When the user asks to check a part of the app against its docs:

1. Find the rules doc and the test files for that part of the app.
2. Run:

   ```bash
   python <this-skill-dir>/scripts/check_rule_coverage.py \
     --rules docs/access-rules.md \
     --tests "tests/**/*auth*" "tests/**/*permission*"
   ```

3. Show the user the MISSING and UNCERTAIN rules.
4. Offer to write a test for each missing rule. Write the tests from the report. Then run the check again to confirm.

Add `--json` for a machine-readable result.

## Run as a hook

The hook runs after Claude edits a file that controls access. If a rule has no test, Claude gets the report.

1. Create `.claude/jev-docs-checker.json` in the project:

   ```json
   {
     "watch": ["src/auth/**", "src/**/permissions*", "src/middleware/**"],
     "rules": "docs/access-rules.md",
     "tests": ["tests/**/*auth*", "tests/**/*permission*"],
     "coveredAt": 0.6,
     "missingBelow": 0.4
   }
   ```

2. Add to `.claude/settings.json`:

   ```json
   {
     "hooks": {
       "PostToolUse": [
         {
           "matcher": "Edit|Write|MultiEdit",
           "hooks": [
             {
               "type": "command",
               "command": "python \"$HOME/.claude/skills/jev-docs-checker/scripts/check_rule_coverage.py\" --hook",
               "timeout": 30
             }
           ]
         }
       ]
     }
   }
   ```

   Change the path if the skill is in a different folder.

The hook does nothing when the edited file does not match `watch`, or when all rules are covered. If Jev fails, the hook writes to stderr and does not stop Claude.

## How it works

- Large test sets are split into groups of about 60,000 characters. All rules are asked against each group in one request. A rule is covered if any group covers it.
- `p_covered` is the Jev probability that a test checks the rule.
- `coveredAt` (0.6) and `missingBelow` (0.4) are first guesses. Tune them on real rules.

## Limits

- Jev judges whether a test **checks** the rule. It does not run the tests. A covered rule can still have a failing test.
- A test file that is longer than 20,000 characters is cut. Split large test files, or point `--tests` at smaller files.
