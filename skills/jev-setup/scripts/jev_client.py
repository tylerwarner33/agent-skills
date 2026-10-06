"""Minimal Jev (TypeSafe System One) client. Uses the Python standard library only.

The other jev-* skills import this file from the sibling jev-setup skill.

Configuration (environment variables):
  AI_GATEWAY_API_KEY  Vercel AI Gateway key. If set, the gateway is used.
  TYPESAFE_API_KEY    TypeSafe key. Used when no gateway key is set.
  JEV_URL             Optional. Override the full systemone endpoint URL.
  JEV_MODEL           Optional. Override the model id.

Run `python jev_client.py` to send one test question.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

GATEWAY_URL = "https://ai-gateway.vercel.sh/typesafe/v1/systemone"
GATEWAY_MODEL = "typesafe-ai/jev"
NATIVE_URL = "https://api.typesafe.ai/v1/systemone"
NATIVE_MODEL = "jev-latest"

RETRY_STATUSES = {429, 529}


class JevError(RuntimeError):
    """A Jev request failed, or Jev is not configured."""


def resolve_config() -> tuple[str, str, str]:
    """Return (url, api_key, model) from the environment."""
    url = os.environ.get("JEV_URL")
    model = os.environ.get("JEV_MODEL")
    gateway_key = os.environ.get("AI_GATEWAY_API_KEY")
    if gateway_key:
        return url or GATEWAY_URL, gateway_key, model or GATEWAY_MODEL
    native_key = os.environ.get("TYPESAFE_API_KEY")
    if native_key:
        return url or NATIVE_URL, native_key, model or NATIVE_MODEL
    raise JevError(
        "Jev is not configured. Set AI_GATEWAY_API_KEY (Vercel AI Gateway) "
        "or TYPESAFE_API_KEY (TypeSafe)."
    )


def ask(state, questions: dict, timeout: float = 20.0, retries: int = 2, extra: dict | None = None) -> dict:
    """Send one System One request and return the `answers` object.

    `questions` maps a question id to a question object (see noul, choice, score).
    All questions in one call share the same state and run in parallel.
    `extra` adds top-level request fields, ex. gateway_fallback(...).
    """
    url, api_key, model = resolve_config()
    payload = {"model": model, "state": state, "questions": questions}
    payload.update(extra or {})
    body = json.dumps(payload).encode("utf-8")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    for attempt in range(retries + 1):
        request = urllib.request.Request(url, data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            answers = payload.get("answers")
            if not isinstance(answers, dict):
                raise JevError("Jev response has no answers object.")
            return answers
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:300]
            if error.code in RETRY_STATUSES and attempt < retries:
                time.sleep(0.5 * (2**attempt))
                continue
            raise JevError(f"Jev request failed ({error.code}): {detail}") from error
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt < retries:
                time.sleep(0.5 * (2**attempt))
                continue
            raise JevError(f"Jev request failed: {error}") from error
    raise JevError("Jev request failed after retries.")


def gateway_fallback(model: str, question: str, confidence_below: float) -> dict:
    """Vercel AI Gateway only: rerun the request on `model` when the Choice or Score
    answer to `question` has a confidence below `confidence_below`. Both stages are billed.
    If a language model gives the final answer, confidence 0 means "not available".
    """
    return {"providerOptions": {"gateway": {"models": [
        {"model": model, "when": {"question": question, "confidenceBelow": confidence_below}},
    ]}}}


def noul(instructions, true: str | None = None, false: str | None = None) -> dict:
    """A yes/no question. The answer is {"noul": P(yes)}."""
    question = {"type": "noul", "instructions": instructions}
    if true or false:
        question["criteria"] = {"true": true or "Yes.", "false": false or "No."}
    return question


def choice(instructions, options: dict[str, str]) -> dict:
    """Pick one option (max 255). The answer has choice, probabilities, confidence."""
    return {"type": "choice", "instructions": instructions, "criteria": options}


def score(instructions, levels: list[str]) -> dict:
    """Rate on 2 to 10 ordered levels. The answer has score, probabilities, confidence."""
    return {"type": "score", "instructions": instructions, "criteria": levels}


if __name__ == "__main__":
    try:
        url, _, model = resolve_config()
        started = time.perf_counter()
        result = ask(
            "I was charged twice for my subscription.",
            {"refund": noul("Is the customer asking for money back?")},
        )
        elapsed = time.perf_counter() - started
    except JevError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
    print(f"OK: {url} model={model} in {elapsed:.2f}s")
    print(json.dumps(result, indent=2))
