---
name: jev-browser-explorer
description: Test a web app in a real browser with Jev choosing where to click next - the skill lists each button and link on the page, Jev picks the one that moves closer to the goal, and the loop repeats until the goal is done or blocked. Claude then compares the trace with the rules in the docs. Use when the user asks to test the app in the browser, check a user flow, or check that each role (ex. admin, manager, employee) can reach only its own pages.
---

# Jev Browser Explorer

A browser test finds problems that only show when a person uses the app. Usually the main model decides each click. This is slow. This skill gives the "where to click next" decision to Jev. Claude still makes the final decision about whether the app works.

The loop:

1. Open the page. List each visible button and link.
2. Jev picks the element that moves closer to the goal, or `goal_done`, or `blocked`.
3. Click it. List the elements on the new page.
4. Repeat until `goal_done`, `blocked`, or the step limit.

The script writes a trace of each step. Claude compares the trace with the rules in the docs.

Requires the `jev-setup` skill (a key in the environment) and Playwright for Python:

```bash
pip install playwright
python -m playwright install chromium
```

## Safety

- Use this skill on a local or test app only. Do not use it on a production site.
- The script never clicks an element whose text matches `--avoid` (default: delete, remove, sign out, pay, and similar words).
- The script does not type passwords. The user signs in one time per role and saves the session (next section).
- Add `.auth/` to `.gitignore`. A saved session is a credential.

## Prepare a session for each role

The user must do this step, because it needs a password. Ask the user to run this command one time for each role, sign in, and close the window:

```bash
python -m playwright codegen --save-storage=.auth/admin.json http://localhost:3000
python -m playwright codegen --save-storage=.auth/manager.json http://localhost:3000
python -m playwright codegen --save-storage=.auth/employee.json http://localhost:3000
```

## Procedure

1. Read the docs that describe the rules for the flow (ex. which role can reach which pages).
2. Make a list of goals to test. For access rules, include goals that each role must **not** reach.
3. Run the script for each role and goal:

   ```bash
   python <this-skill-dir>/scripts/explore_app.py \
     --url http://localhost:3000 \
     --goal "Open the payroll report for all employees" \
     --role employee \
     --storage-state .auth/employee.json \
     --out .jev/employee-payroll.json
   ```

   Add `--headed` to watch the browser. Use `--max-steps` to change the limit (default 15).

4. Read each trace. Compare `result`, `final_url`, and the steps with the rules:
   - A role reached a page that it must not reach: report a **violation**.
   - A role was `blocked` from a page that it must reach: report a **bug**.
   - `max_steps` or `error`: the test is not complete. Try a more specific goal, or check the app by hand.
5. Give the user a table: role, goal, expected, actual, and status.

## Trace example

```json
{
  "goal": "Open the payroll report for all employees",
  "role": "employee",
  "result": "blocked",
  "steps": [
    {"step": 1, "url": "http://localhost:3000/", "pick": "e4", "label": "link 'Reports' -> /reports", "confidence": 0.88},
    {"step": 2, "url": "http://localhost:3000/reports", "pick": "blocked", "confidence": 0.81}
  ],
  "final_url": "http://localhost:3000/reports",
  "seconds": 4.2
}
```

## Limits

- The script clicks only. It does not fill forms. For a flow that needs input, test that part with the normal browser tool.
- Jev sees the first 3,000 characters of the page text and up to 250 elements.
- `goal_done` is Jev's opinion. Claude must check the final page against the docs before it reports a pass.
