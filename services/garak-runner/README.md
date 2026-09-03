# garak-runner

A small, real HTTP sidecar wrapping [garak](https://github.com/NVIDIA/garak) — NVIDIA's
open-source LLM vulnerability scanner (Apache 2.0, no vendor API). Built for
`securing-ai-demo`'s Detect phase, which already has a live-connector client
(`app/mcp/client.py`'s `trigger_runner_scan`) ready to call a self-hosted runner at
`GARAK_RUNNER_URL` — this *is* that runner.

## Why this exists

Garak and PyRIT are genuinely free, but neither has a hosted API — you run them yourself
and point a caller at your own runner's URL. This project is that runner for garak: a
FastAPI service exposing the minimal contract `securing-ai-demo` already expects.

## Contract

```
POST /run
{"target": "http://host/chat", "probes": ["dan.DAN_Jailbreak", ...], "target_label": "..."}

-> {"success": bool, "findings": [...], "probes_run": [...], "target": "..."}
```

Internally this shells out to the real `garak` CLI against garak's built-in generic REST
generator (`--target_type rest`), pointed at whatever `target` URL is given — no changes
needed to the target service itself, as long as it accepts a JSON POST and replies with a
JSON field containing the text. Configured in `main.py` for `securing-ai-demo`'s target
agent shape (`{"message": "$INPUT", "provider": "groq"}` request, `reply` response field);
adjust `req_template_json_object` / `response_json_field` there for a different target.

Default probe set (`DEFAULT_PROBES` in `main.py`) is four real, single-prompt garak
jailbreak probes (`dan.DAN_Jailbreak`, `dan.AntiDAN`, `dan.STAN`,
`dan.ChatGPT_Developer_Mode_v2`) — real garak, kept small so a scan finishes in a few
minutes rather than garak's full suite. Override per-request via `"probes"` for a broader
real scan (see `garak --list_probes` for the full catalog).

Each finding combines two real signals from the same real run: garak's own
`garak_detector_results` (its standardized jailbreak-compliance scoring) and a direct
`canary_leaked` check against `GARAK_CANARY_FRAGMENT` (env var, defaults to
`securing-ai-demo`'s real canary secret) — parsed straight out of garak's own JSONL
report, not a second scan.

## Setup

```bash
uv venv --python 3.12   # garak needs >=3.10; 3.12 avoids brand-new-Python dependency churn
uv pip install -r requirements.txt
```

## Run

```bash
.venv/Scripts/python -m uvicorn main:app --host 127.0.0.1 --port 8095
```

Then in `securing-ai-demo`'s `.env`:

```
GARAK_RUNNER_URL=http://127.0.0.1:8095
```

## A real gotcha worth knowing if you touch `main.py`

garak's `--generator_option_file` JSON is combined *directly* into
`_config.plugins.generators` (see `garak/cli.py`'s `parse_cli_plugin_config` +
`_combine_into`) — the file itself must NOT repeat the outer `"generators"` key, or every
setting lands one level too deep and garak reports `"No REST endpoint URI definition
found"` despite a `uri` being present. Correct shape: `{"rest": {"RestGenerator": {...}}}`,
not `{"generators": {"rest": {"RestGenerator": {...}}}}`. Verified empirically against the
installed garak 0.16.0, not just inferred from source.

Also: garak writes each real attempt to its JSONL report *twice* — once at generation time
(`detector_results` empty) and again after evaluation (populated). `main.py` dedupes by
`uuid`, keeping the last write, to avoid double-counting every real finding.

## Runtime

A real scan is genuinely slower than a typical API call — the default 4-probe/20-generation
set measured ~190s end to end against a real target. `securing-ai-demo`'s client-side
timeout for this call is set accordingly (330s, in `app/mcp/client.py`'s
`trigger_runner_scan`); if you widen the probe set, widen that timeout to match.
