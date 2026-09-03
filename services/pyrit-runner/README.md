# pyrit-runner

A small, real HTTP sidecar wrapping [PyRIT](https://github.com/Azure/PyRIT) — Microsoft's
open-source Python Risk Identification Toolkit (MIT license, no vendor API). Same role and
contract as `../garak-runner`, for `securing-ai-demo`'s Detect phase.

## Contract

Identical to `garak-runner`'s:

```
POST /run
{"target": "http://host/chat", "probes": ["dan_11", ...], "target_label": "...", "objective_ask": "..."}

-> {"success": bool, "findings": [...], "probes_run": [...], "target": "...", "errors": [...] | null}
```

## Real mechanism

Uses PyRIT's own real, documented pattern for hitting an arbitrary REST endpoint —
`HTTPTarget` with a raw HTTP request string and a `{PROMPT}` placeholder, substituted by
PyRIT itself before sending (see `_build_http_target` in `main.py`). Points directly at the
real target's `/chat` endpoint; no changes needed to the target itself.

Default probe set (`DEFAULT_PROBES`) is four real jailbreak templates PyRIT genuinely ships
(`pyrit/datasets/jailbreak/templates/*.yaml` — not authored by this project), each rendered
with a real extraction objective (`DEFAULT_OBJECTIVE_ASK`) via PyRIT's real `SeedPrompt`
templating, then sent through PyRIT's real `PromptSendingAttack`. Override `"probes"` with
other template stem names from that directory for a broader real scan; override
`"objective_ask"` to test a different real ask.

No PyRIT scorer is configured — `canary_leaked` is this runner's own direct check against
`PYRIT_CANARY_FRAGMENT` (env var, defaults to `securing-ai-demo`'s real canary), parsed
straight from the real `AttackResult.last_response`. Kept deliberately separate from any
future PyRIT-native scoring, same reasoning as garak-runner keeping its own canary check
distinct from garak's own detector verdicts.

## Setup

```bash
uv venv --python 3.12
uv pip install -r requirements.txt
```

## Run

```bash
.venv/Scripts/python -m uvicorn main:app --host 127.0.0.1 --port 8096
```

Then in `securing-ai-demo`'s `.env`:

```
PYRIT_RUNNER_URL=http://127.0.0.1:8096
```

## A real gotcha worth knowing if you touch `main.py`

`HTTPTarget._inject_prompt_into_request` substitutes the **raw** objective text directly
into `{PROMPT}` in the request template — no JSON escaping of its own. Several of PyRIT's
real jailbreak templates (`aim`, `based_gpt_1`, ...) contain literal double-quotes in their
real prompt text, which — substituted raw into `"message": "{PROMPT}"` — broke the JSON
body and made the target 422 on those probes specifically. Symptom: `response_snippet`
comes back empty for exactly the templates containing quotes, while others succeed, and the
whole batch finishes suspiciously fast (the failures are near-instant 422s, not real LLM
calls). Fixed by passing `json.dumps(rendered)[1:-1]` (the JSON-escaped form, minus the
outer quotes) as the `objective` to `execute_async`, so whatever gets substituted is already
valid inside the surrounding quotes — the unescaped `rendered` text is kept separately only
for a readable `"prompt"` field in the finding. Verified empirically: all four default
probes return full real responses after this fix, none did before it for the two
quote-containing templates.

## Runtime

Much faster than garak-runner's default scan — the four-template/one-generation-each set
measured ~5s end to end (PyRIT here does one real call per probe, vs. garak's default five
generations per probe). `securing-ai-demo`'s shared 330s runner-scan timeout comfortably
covers this; no separate tuning needed. If you run garak and pyrit back to back against the
same free-tier LLM backend, pyrit's calls can hit real rate-limit errors from garak's
preceding ~150-190s of continuous calls — a real infrastructure interaction, not a bug in
either runner; failures land in the response's `errors` list rather than silently vanishing.
