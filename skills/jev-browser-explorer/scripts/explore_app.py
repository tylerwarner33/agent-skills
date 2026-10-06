"""Jev drives a browser toward a goal. Requires Playwright for Python.

Each step: list the visible buttons and links, Jev picks the one that moves closer
to the goal (or "goal_done" or "blocked"), the script clicks it, and repeats.
The script writes a trace. Claude compares the trace with the rules in the docs.

  python explore_app.py --url http://localhost:3000 \
    --goal "Open the payroll report" \
    --storage-state .auth/employee.json --out .jev/employee-payroll.json

Make a signed-in session one time per role (the user signs in by hand):
  python -m playwright codegen --save-storage=.auth/employee.json http://localhost:3000
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "jev-setup" / "scripts"))
from jev_client import JevError, ask, choice  # noqa: E402

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright is not installed. Run: pip install playwright && python -m playwright install chromium", file=sys.stderr)
    sys.exit(1)

MAX_ELEMENTS = 250  # 255 Jev options minus the stop options
PAGE_TEXT_CHARS = 3_000
DEFAULT_AVOID = r"\b(delete|remove|destroy|drop|sign ?out|log ?out|unsubscribe|deactivate|pay|purchase)\b"

LIST_ELEMENTS_JS = """
() => {
  const selector = 'a[href], button, [role=button], [role=link], [role=tab], [role=menuitem], input[type=submit], input[type=button]';
  const items = [];
  document.querySelectorAll('[data-jev-id]').forEach(el => el.removeAttribute('data-jev-id'));
  for (const el of document.querySelectorAll(selector)) {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    if (rect.width === 0 || rect.height === 0 || style.visibility === 'hidden' || style.display === 'none') continue;
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
    const text = (el.innerText || el.getAttribute('aria-label') || el.value || el.title || '').trim().replace(/\\s+/g, ' ').slice(0, 80);
    if (!text) continue;
    const id = 'e' + items.length;
    el.setAttribute('data-jev-id', id);
    items.push({ id, kind: el.tagName.toLowerCase() === 'a' ? 'link' : 'button', text, href: el.getAttribute('href') || '' });
  }
  return items;
}
"""


def describe(element: dict) -> str:
    target = f" -> {element['href']}" if element["href"] and not element["href"].startswith("javascript") else ""
    return f"{element['kind']} '{element['text']}'{target}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True, help="Start URL. Use a local or test app only.")
    parser.add_argument("--goal", required=True, help="What to reach, in plain words.")
    parser.add_argument("--storage-state", help="Saved signed-in session (Playwright storage state).")
    parser.add_argument("--role", default="", help="Label for the trace, ex. admin.")
    parser.add_argument("--max-steps", type=int, default=15)
    parser.add_argument("--avoid", default=DEFAULT_AVOID, help="Regex. Never click elements whose text matches.")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--out", help="Write the trace JSON to this file.")
    args = parser.parse_args()

    avoid = re.compile(args.avoid, re.IGNORECASE) if args.avoid else None
    trace = {"goal": args.goal, "role": args.role, "start_url": args.url, "steps": [], "result": "max_steps"}
    history: list[str] = []
    started = time.perf_counter()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed)
        context = browser.new_context(storage_state=args.storage_state) if args.storage_state else browser.new_context()
        page = context.new_page()
        page.goto(args.url, wait_until="domcontentloaded")

        for step in range(args.max_steps):
            try:
                page.wait_for_load_state("networkidle", timeout=5_000)
            except PlaywrightError:
                pass
            elements = [e for e in page.evaluate(LIST_ELEMENTS_JS) if not (avoid and avoid.search(e["text"]))][:MAX_ELEMENTS]
            options = {e["id"]: describe(e) for e in elements}
            options["goal_done"] = "The goal is reached. The current page shows what the goal asks for."
            options["blocked"] = "The goal cannot be reached from here, ex. access denied, an error, or no path forward."

            state = {
                "goal": args.goal,
                "current_page": {"url": page.url, "title": page.title(), "text": page.inner_text("body")[:PAGE_TEXT_CHARS]},
                "steps_so_far": history,
            }
            question = choice(
                "To move closer to `goal`, which element on `current_page` must be clicked next? "
                "Do not repeat a step in `steps_so_far` unless it is necessary. "
                "Pick goal_done if the page already shows what the goal asks for. "
                "Pick blocked if the page denies access, shows an error, or has no path to the goal.",
                options,
            )
            try:
                answer = ask(state, {"next": question})["next"]
            except JevError as error:
                trace["result"] = "error"
                trace["error"] = str(error)
                break

            picked = answer.get("choice")
            record = {"step": step + 1, "url": page.url, "title": page.title(), "pick": picked,
                      "label": options.get(picked, ""), "confidence": round(answer.get("confidence", 0.0), 3)}
            trace["steps"].append(record)
            if picked in ("goal_done", "blocked"):
                trace["result"] = picked
                break

            history.append(f"On {page.url}: clicked {options.get(picked, picked)}")
            try:
                page.locator(f'[data-jev-id="{picked}"]').first.click(timeout=5_000)
            except PlaywrightError as error:
                record["click_error"] = str(error).splitlines()[0]
                history.append(f"The click failed: {record['click_error']}")

        trace["final_url"] = page.url
        trace["final_title"] = page.title()
        browser.close()

    trace["seconds"] = round(time.perf_counter() - started, 2)
    output = json.dumps(trace, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(output, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
