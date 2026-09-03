"""
Securing AI — MCP Client
Real HTTP integrations for the 5 tools in the registry (app/mcp/registry.py):
Lakera Guard, Garak, PyRIT, Jira, ServiceNow. Each capability method calls the
real vendor/runner API when credentials are configured, and returns a clearly
labelled mock result otherwise — never silently pretends a mock result is
live data.
"""

from __future__ import annotations

import base64
import os
import random
import time
from typing import Any, Dict, List, Optional

import httpx

from app.mcp.registry import MCPToolRegistry, MCPToolMetadata
from app.observability.audit_logger import AuditLogger

_TIMEOUT = 15.0


class MCPClient:
    """Manages connection status and real HTTP calls for the registered MCP tools."""

    def __init__(self, registry: Optional[MCPToolRegistry] = None) -> None:
        self.registry = registry or MCPToolRegistry()

    # ── Status ───────────────────────────────────────────────────────────

    def _resolve_env(self, tool: MCPToolMetadata) -> Dict[str, Optional[str]]:
        return {var: os.getenv(var) for var in tool.required_env_vars}

    def get_connection_status(self, tool_name: str) -> Dict[str, Any]:
        """Check the connection status and environment variable availability of a tool."""
        tool = self.registry.get_tool(tool_name)
        if not tool:
            return {"status": "Disconnected", "error": f"Tool '{tool_name}' not found in registry.", "live": False}

        env_vars = self._resolve_env(tool)
        has_creds = all(env_vars.values())

        if has_creds:
            return {
                "status": "Connected (Live)",
                "live": True,
                "error": None,
                "creds_found": list(env_vars.keys()),
            }
        return {
            "status": "Connected (Mock Fallback)",
            "live": False,
            "error": "Missing configuration. Operating in mock mode.",
            "missing_creds": [v for v in tool.required_env_vars if not env_vars.get(v)],
        }

    # ── Lakera Guard — real-time prompt screening ───────────────────────

    def screen_prompt(self, text: str) -> Dict[str, Any]:
        """Screen a single piece of text via Lakera Guard's /v2/guard endpoint.
        Real call when LAKERA_API_KEY is set; a clearly-labelled mock result
        otherwise. https://platform.lakera.ai/docs"""
        status = self.get_connection_status("lakera_guard")
        env = self._resolve_env(self.registry.get_tool("lakera_guard"))

        if status["live"]:
            try:
                resp = httpx.post(
                    "https://api.lakera.ai/v2/guard",
                    headers={"Authorization": f"Bearer {env['LAKERA_API_KEY']}"},
                    json={"messages": [{"role": "user", "content": text}]},
                    timeout=_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()
                return {
                    "live": True,
                    "flagged": bool(data.get("flagged", False)),
                    "raw": data,
                }
            except Exception as exc:
                return {"live": True, "error": f"Lakera Guard call failed: {exc}", "flagged": None}

        # Mock fallback — deterministic, clearly not live
        flagged = any(kw in text.lower() for kw in ["ignore previous", "jailbreak", "dan mode", "system prompt"])
        return {
            "live": False,
            "flagged": flagged,
            "raw": {"mock": True, "note": "LAKERA_API_KEY not configured — heuristic mock result, not a real Lakera verdict."},
        }

    # ── Garak / PyRIT — self-hosted runner scan trigger ──────────────────

    def trigger_runner_scan(self, tool_name: str, target: str, probes: Optional[List[str]] = None, target_label: Optional[str] = None) -> Dict[str, Any]:
        """POST to the user's own Garak/PyRIT runner. There is no public
        vendor API for either tool — this calls whatever URL is configured
        in GARAK_RUNNER_URL / PYRIT_RUNNER_URL, using a minimal contract we
        define ourselves: POST {url}/run with {"target", "probes"}, expects
        back {"success": bool, "findings": [...]}."""
        tool = self.registry.get_tool(tool_name)
        if not tool or tool.integration_type != "self_hosted_runner":
            raise ValueError(f"'{tool_name}' is not a self-hosted-runner tool.")

        status = self.get_connection_status(tool_name)
        env = self._resolve_env(tool)
        runner_url_var = tool.required_env_vars[0]  # GARAK_RUNNER_URL / PYRIT_RUNNER_URL

        if status["live"]:
            base_url = (env[runner_url_var] or "").rstrip("/")
            try:
                # A real scan (multiple real probes x real generations,
                # each a real call to the target's own LLM) genuinely takes
                # longer than the quick-API-call _TIMEOUT every other tool
                # here uses — 15s (and, empirically, even 180s) was silently
                # truncating real garak runs to "no findings" via the except
                # branch below, not a real scan result. The real default
                # 4-probe/20-generation run measured ~190s end to end;
                # 330s gives real headroom above the runner's own 300s
                # internal subprocess timeout (GARAK_RUN_TIMEOUT) so this
                # client is never the one cutting a real scan off early.
                payload = {"target": target, "probes": probes or []}
                if target_label:
                    payload["target_label"] = target_label
                resp = httpx.post(f"{base_url}/run", json=payload, timeout=330.0)
                resp.raise_for_status()
                data = resp.json()
                return {"live": True, "success": data.get("success", True), "findings": data.get("findings", []), "raw": data}
            except Exception as exc:
                return {"live": True, "error": f"{tool.display_name} runner call failed: {exc}", "success": False, "findings": []}

        return {
            "live": False,
            "success": True,
            "findings": [],
            "note": f"{runner_url_var} not configured — no self-hosted {tool.display_name} runner to call.",
        }

    # ── Jira / ServiceNow — real ticket creation ─────────────────────────

    def create_ticket(self, tool_name: str, summary: str, description: str, priority: str = "Medium") -> Dict[str, Any]:
        """Create a real ticket via Jira or ServiceNow's REST API when
        configured; a mock reference number otherwise."""
        tool = self.registry.get_tool(tool_name)
        if not tool or "write_ticket" not in tool.capabilities:
            raise ValueError(f"Tool {tool_name} does not support write_ticket capability.")

        status = self.get_connection_status(tool_name)
        env = self._resolve_env(tool)

        if status["live"] and tool_name == "jira":
            return self._create_jira_ticket(env, summary, description)
        if status["live"] and tool_name == "servicenow":
            return self._create_servicenow_ticket(env, summary, description, priority)

        # Mock fallback
        ticket_ref = f"{tool_name.upper()}-{random.randint(45000, 99000)}"
        AuditLogger().log_action(
            action=f"Create Ticket ({tool.display_name}) — Mock",
            username="api_user", status="Success", target=ticket_ref,
            details=f"{tool.display_name} not configured — simulated ticket. summary={summary!r}",
        )
        return {"live": False, "success": True, "ticket_ref": ticket_ref, "url": None}

    def _create_jira_ticket(self, env: Dict[str, Optional[str]], summary: str, description: str) -> Dict[str, Any]:
        jira_url = (env["JIRA_URL"] or "").rstrip("/")
        auth = base64.b64encode(f"{env['JIRA_USERNAME']}:{env['JIRA_API_TOKEN']}".encode()).decode()
        try:
            resp = httpx.post(
                f"{jira_url}/rest/api/2/issue",
                headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
                json={
                    "fields": {
                        "project": {"key": env["JIRA_PROJECT_KEY"]},
                        "summary": summary,
                        "description": description,
                        "issuetype": {"name": "Task"},
                    }
                },
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            ticket_ref = data.get("key", "UNKNOWN")
            AuditLogger().log_action(
                action="Create Ticket (Jira) — Live", username="api_user", status="Success",
                target=ticket_ref, details=f"Created real Jira issue {ticket_ref}: {summary}",
            )
            return {"live": True, "success": True, "ticket_ref": ticket_ref, "url": f"{jira_url}/browse/{ticket_ref}"}
        except Exception as exc:
            AuditLogger().log_action(
                action="Create Ticket (Jira) — Failed", username="api_user", status="Failed",
                target=summary, details=f"Jira API call failed: {exc}",
            )
            return {"live": True, "success": False, "error": str(exc)}

    def _create_servicenow_ticket(self, env: Dict[str, Optional[str]], summary: str, description: str, priority: str) -> Dict[str, Any]:
        instance = env["SERVICENOW_INSTANCE"]
        urgency = {"Critical": "1", "High": "2", "Medium": "3", "Low": "4"}.get(priority, "3")
        try:
            resp = httpx.post(
                f"https://{instance}.service-now.com/api/now/table/incident",
                auth=(env["SERVICENOW_USERNAME"], env["SERVICENOW_PASSWORD"]),
                headers={"Content-Type": "application/json"},
                json={"short_description": summary, "description": description, "urgency": urgency, "impact": urgency},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json().get("result", {})
            ticket_ref = data.get("number", "UNKNOWN")
            AuditLogger().log_action(
                action="Create Ticket (ServiceNow) — Live", username="api_user", status="Success",
                target=ticket_ref, details=f"Created real ServiceNow incident {ticket_ref}: {summary}",
            )
            return {"live": True, "success": True, "ticket_ref": ticket_ref, "url": f"https://{instance}.service-now.com/nav_to.do?uri=incident.do?sys_id={data.get('sys_id', '')}"}
        except Exception as exc:
            AuditLogger().log_action(
                action="Create Ticket (ServiceNow) — Failed", username="api_user", status="Failed",
                target=summary, details=f"ServiceNow API call failed: {exc}",
            )
            return {"live": True, "success": False, "error": str(exc)}

    # ── Live demo targets — GitHub, target_agent, Slack ──────────────────
    # Deliberately no mock fallback in this section, unlike the 5 methods
    # above. A failure here raises with the real cause; callers (the run-
    # stage endpoint in backend/main.py) let it surface as a real error to
    # the frontend rather than degrading to fabricated content — see
    # AGENTS.md's live-demo notes for why.

    class LiveConnectorError(RuntimeError):
        """Raised by the github/target_agent/slack methods on any failure —
        missing config, HTTP error, unexpected response shape. Always
        carries the real cause in its message."""

    def _require_env_for(self, tool_name: str) -> Dict[str, str]:
        tool = self.registry.get_tool(tool_name)
        env = self._resolve_env(tool)
        missing = [v for v in tool.required_env_vars if not env.get(v)]
        if missing:
            raise MCPClient.LiveConnectorError(
                f"{tool.display_name} is not configured — missing env var(s): {', '.join(missing)}"
            )
        return env  # type: ignore[return-value]

    # ── GitHub ─────────────────────────────────────────────────────────

    def _github_headers(self, env: Dict[str, str]) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {env['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _github_request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        env = self._require_env_for("github")
        repo = env["GITHUB_TARGET_REPO"]  # "owner/name"
        try:
            resp = httpx.request(method, f"https://api.github.com/repos/{repo}{path}", headers=self._github_headers(env), timeout=_TIMEOUT, **kwargs)
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as exc:
            raise MCPClient.LiveConnectorError(f"GitHub API {method} {path} failed: {exc.response.status_code} {exc.response.text[:300]}") from exc
        except httpx.HTTPError as exc:
            raise MCPClient.LiveConnectorError(f"GitHub API {method} {path} failed: {exc}") from exc

    def github_get_repo_info(self) -> Dict[str, Any]:
        """Real repo metadata — created_at, description, default_branch, etc."""
        resp = self._github_request("GET", "")
        return resp.json()

    def github_get_file(self, path: str) -> Dict[str, Any]:
        """Real file content from the target repo (e.g. governance/policy.yaml,
        requirements.txt) via the Contents API. Returns {"content": <decoded text>, "sha": ...}."""
        resp = self._github_request("GET", f"/contents/{path}")
        data = resp.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        return {"path": path, "content": content, "sha": data["sha"]}

    def github_get_repo_tree(self, branch: str = "main") -> List[Dict[str, Any]]:
        """Real recursive file tree — used by Identify to discover what's in the repo."""
        resp = self._github_request("GET", f"/git/trees/{branch}?recursive=1")
        return resp.json().get("tree", [])

    def github_get_dependabot_alerts(self) -> List[Dict[str, Any]]:
        resp = self._github_request("GET", "/dependabot/alerts?state=open")
        return resp.json()

    def github_get_secret_scanning_alerts(self) -> List[Dict[str, Any]]:
        resp = self._github_request("GET", "/secret-scanning/alerts?state=open")
        return resp.json()

    def github_get_branch_protection(self, branch: str = "main") -> Dict[str, Any]:
        resp = self._github_request("GET", f"/branches/{branch}/protection")
        return resp.json()

    def github_get_collaborators(self) -> List[Dict[str, Any]]:
        resp = self._github_request("GET", "/collaborators")
        return resp.json()

    def github_get_commit_history(self, branch: str = "main", limit: int = 10) -> List[Dict[str, Any]]:
        """Real commit history — each commit's real `parents` list tells us
        whether it genuinely has something to roll back to."""
        resp = self._github_request("GET", f"/commits?sha={branch}&per_page={limit}")
        return resp.json()

    def github_get_latest_workflow_run(self, workflow_file: str = "guardrail-check.yml") -> Dict[str, Any]:
        resp = self._github_request("GET", f"/actions/workflows/{workflow_file}/runs?per_page=1")
        runs = resp.json().get("workflow_runs", [])
        return runs[0] if runs else {}

    def github_revoke_collaborator(self, username: str) -> Dict[str, Any]:
        """Real Respond action: remove a collaborator's real access to the target repo."""
        self._github_request("DELETE", f"/collaborators/{username}")
        AuditLogger().log_action(action="Revoke GitHub Collaborator — Live", username="api_user", status="Success", target=username, details=f"Removed {username} from the target repo (real GitHub API call).")
        return {"live": True, "revoked": username}

    def github_set_workflow_state(self, enable: bool, workflow_file: str = "guardrail-check.yml") -> Dict[str, Any]:
        """Real Respond (disable) / Recover (enable) action on the target repo's Actions workflow."""
        action = "enable" if enable else "disable"
        self._github_request("PUT", f"/actions/workflows/{workflow_file}/{action}")
        AuditLogger().log_action(action=f"GitHub Workflow {action.title()} — Live", username="api_user", status="Success", target=workflow_file, details=f"Real {action} call against the target repo's workflow.")
        return {"live": True, "workflow": workflow_file, "enabled": enable}

    def github_revert_last_commit(self, branch: str = "main") -> Dict[str, Any]:
        """Real Recover action: creates a real new commit on the target repo
        whose tree matches the parent of the current HEAD (i.e. reverts the
        most recent commit's changes), and moves the branch ref to it."""
        ref_resp = self._github_request("GET", f"/git/ref/heads/{branch}")
        head_sha = ref_resp.json()["object"]["sha"]

        head_commit = self._github_request("GET", f"/git/commits/{head_sha}").json()
        parents = head_commit.get("parents", [])
        if not parents:
            raise MCPClient.LiveConnectorError("HEAD commit has no parent — nothing to revert to.")
        parent_sha = parents[0]["sha"]
        parent_commit = self._github_request("GET", f"/git/commits/{parent_sha}").json()

        new_commit = self._github_request("POST", "/git/commits", json={
            "message": f"Revert: restore state prior to {head_sha[:7]} (real Recover action from securing-ai-demo)",
            "tree": parent_commit["tree"]["sha"],
            "parents": [head_sha],
        }).json()

        self._github_request("PATCH", f"/git/refs/heads/{branch}", json={"sha": new_commit["sha"]})
        AuditLogger().log_action(action="GitHub Revert — Live", username="api_user", status="Success", target=new_commit["sha"], details=f"Real revert commit {new_commit['sha']} created on {branch}, reverting {head_sha}.")
        return {"live": True, "reverted_from": head_sha, "new_commit": new_commit["sha"]}

    # ── Target agent (meridian-support-agent) ─────────────────────────

    def target_agent_chat(self, message: str, provider: str = "groq") -> Dict[str, Any]:
        env = self._require_env_for("target_agent")
        base = env["TARGET_AGENT_URL"].rstrip("/")
        try:
            resp = httpx.post(f"{base}/chat", json={"message": message, "provider": provider}, timeout=_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 503:
                return {"reply": None, "provider": provider, "disabled": True}
            raise MCPClient.LiveConnectorError(f"target_agent /chat failed: {exc.response.status_code} {exc.response.text[:300]}") from exc
        except httpx.HTTPError as exc:
            raise MCPClient.LiveConnectorError(f"target_agent /chat failed: {exc}") from exc

    def target_agent_healthz(self) -> Dict[str, Any]:
        """Real, cheap GET status check — {"status": "ok", "disabled": bool}
        — no LLM call involved, unlike target_agent_chat. Used at process
        startup to detect and self-heal a target agent left disabled by a
        prior session's Respond test (see AppState.init())."""
        env = self._require_env_for("target_agent")
        base = env["TARGET_AGENT_URL"].rstrip("/")
        resp = httpx.get(f"{base}/healthz", timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def target_agent_set_disabled(self, disabled: bool) -> Dict[str, Any]:
        """Real Respond (disable) / Recover (enable) action against the real deployed target agent."""
        env = self._require_env_for("target_agent")
        base = env["TARGET_AGENT_URL"].rstrip("/")
        path = "disable" if disabled else "enable"
        try:
            resp = httpx.post(f"{base}/admin/{path}", headers={"Authorization": f"Bearer {env['TARGET_AGENT_ADMIN_TOKEN']}"}, timeout=_TIMEOUT)
            resp.raise_for_status()
            AuditLogger().log_action(action=f"Target Agent {'Disable' if disabled else 'Enable'} — Live", username="api_user", status="Success", target=base, details=f"Real /admin/{path} call.")
            return resp.json()
        except httpx.HTTPError as exc:
            raise MCPClient.LiveConnectorError(f"target_agent /admin/{path} failed: {exc}") from exc

    def target_agent_set_guardrail_enabled(self, enabled: bool) -> Dict[str, Any]:
        """Toggles the target agent's real output-side guardrail (2b89c37) —
        distinct from target_agent_set_disabled above, which stops the agent
        entirely. Every real caller (capture-historical-leak, Detect's live
        vulnerability demo) wraps this in a try/finally that guarantees it
        always ends back on True. Real admin-token-authenticated call, same
        as the disable/enable pair."""
        env = self._require_env_for("target_agent")
        base = env["TARGET_AGENT_URL"].rstrip("/")
        path = "guardrail/disable" if not enabled else "guardrail/enable"
        try:
            resp = httpx.post(f"{base}/admin/{path}", headers={"Authorization": f"Bearer {env['TARGET_AGENT_ADMIN_TOKEN']}"}, timeout=_TIMEOUT)
            resp.raise_for_status()
            AuditLogger().log_action(
                action=f"Target Agent Guardrail {'Enable' if enabled else 'Disable'} — Live",
                username="api_user", status="Success", target=base, details=f"Real /admin/{path} call.",
            )
            return resp.json()
        except httpx.HTTPError as exc:
            raise MCPClient.LiveConnectorError(f"target_agent /admin/{path} failed: {exc}") from exc

    # ── External Source (bring-your-own SIEM / API) ──────────────────────

    def external_source_fetch_events(self) -> List[Dict[str, Any]]:
        """Real, generic GET against whatever SIEM_API_URL a user has
        configured — Bearer-auth'd with SIEM_API_KEY. There's no specific
        real vendor behind this (unlike Lakera/Garak/PyRIT above), so this
        has never been exercised against a real SIEM in this project; it's
        genuinely wireable real code, not a mock, for whenever one is
        connected. Expects a JSON body shaped either as a bare list of
        events or {"events": [...]} — the two most common REST shapes —
        and raises LiveConnectorError on anything else so a shape mismatch
        surfaces as a real, specific error instead of silently returning
        nothing."""
        env = self._require_env_for("external_source")
        try:
            resp = httpx.get(
                env["SIEM_API_URL"],
                headers={"Authorization": f"Bearer {env['SIEM_API_KEY']}"},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise MCPClient.LiveConnectorError(f"External source fetch failed: {exc}") from exc

        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("events"), list):
            return data["events"]
        raise MCPClient.LiveConnectorError(
            "External source returned an unexpected shape (expected a JSON list or {\"events\": [...]})."
        )

    # ── Slack ──────────────────────────────────────────────────────────

    def slack_post_approval_request(self, incident_summary: str, action_id: str) -> Dict[str, Any]:
        """Posts a real Slack message with real interactive Approve/Reject
        buttons. `action_id` is an opaque token backend/main.py uses to look
        up what the buttons should do when Slack calls back to
        POST /api/slack/interactions."""
        env = self._require_env_for("slack")
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": f":rotating_light: *Securing AI — approval required*\n{incident_summary}"}},
            {"type": "actions", "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "Approve"}, "style": "primary", "action_id": "approve", "value": action_id},
                {"type": "button", "text": {"type": "plain_text", "text": "Reject"}, "style": "danger", "action_id": "reject", "value": action_id},
            ]},
        ]
        try:
            resp = httpx.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {env['SLACK_BOT_TOKEN']}"},
                json={"channel": env["SLACK_CHANNEL_ID"], "text": incident_summary, "blocks": blocks},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                raise MCPClient.LiveConnectorError(f"Slack chat.postMessage failed: {data.get('error')}")
            channel, ts = data.get("channel"), data.get("ts")

            # Real deep link straight to this message — lets a live demo
            # jump directly to the Approve/Reject buttons in Slack instead
            # of hunting for the channel manually. Best-effort: a failure
            # here doesn't undo the real post above, it just means the UI
            # falls back to naming the channel instead of linking to it.
            permalink = None
            try:
                perm_resp = httpx.get(
                    "https://slack.com/api/chat.getPermalink",
                    headers={"Authorization": f"Bearer {env['SLACK_BOT_TOKEN']}"},
                    params={"channel": channel, "message_ts": ts},
                    timeout=_TIMEOUT,
                )
                perm_data = perm_resp.json()
                if perm_data.get("ok"):
                    permalink = perm_data.get("permalink")
            except httpx.HTTPError:
                pass

            return {"live": True, "channel": channel, "ts": ts, "permalink": permalink}
        except httpx.HTTPError as exc:
            raise MCPClient.LiveConnectorError(f"Slack chat.postMessage failed: {exc}") from exc
