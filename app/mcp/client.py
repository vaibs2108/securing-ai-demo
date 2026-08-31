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

    def trigger_runner_scan(self, tool_name: str, target: str, probes: Optional[List[str]] = None) -> Dict[str, Any]:
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
                resp = httpx.post(
                    f"{base_url}/run",
                    json={"target": target, "probes": probes or []},
                    timeout=_TIMEOUT,
                )
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
