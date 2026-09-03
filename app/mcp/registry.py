"""
Securing AI — MCP Tool Registry
Catalogues only tools that are (a) real, specifically-named products/projects
and (b) genuinely wireable — either a real hosted vendor API with key-based
auth, or a well-known open-source scanner you self-host and point us at.

Deliberately excludes generic category placeholders ("AI-SPM Scanner", "SOAR
Platform" — no specific real product) and tools whose primary usage pattern
doesn't fit an external-API-with-a-key shape (Guardrails AI is a Python
library you import, not a service you call) or whose current exact API
specifics aren't confidently known (Protect AI Guardian, HiddenLayer AISec —
real companies, but not enough certainty here to build a correct integration
without guessing at endpoints).
"""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

class MCPToolMetadata(BaseModel):
    """Metadata representing a single security tool integration in the MCP registry."""
    name: str = Field(..., description="Unique tool name (e.g. lakera_guard, jira)")
    display_name: str = Field(..., description="User-friendly display name (e.g. Lakera Guard)")
    category: str = Field(..., description="AI Security|Remediation")
    description: str = Field(..., description="Short explanation of what the tool does")
    capabilities: List[str] = Field(default_factory=list, description="Supported operations: screen_input, execute_scan, write_ticket, etc.")
    endpoints: Dict[str, str] = Field(default_factory=dict, description="Resource paths mapped to logical actions")
    required_env_vars: List[str] = Field(default_factory=list, description="Variables needed in .env to activate live mode")
    integration_type: Literal["hosted_api", "self_hosted_runner"] = Field(
        "hosted_api",
        description="hosted_api = a real vendor-hosted API reachable with just an API key. "
                     "self_hosted_runner = a real open-source tool you run yourself; what you "
                     "configure is the URL of YOUR runner, not a vendor API key.",
    )
    docs_url: str = Field("", description="Where to find the real, current API/setup docs")

class MCPToolRegistry:
    """Main registry for tool configuration and validation."""

    def __init__(self) -> None:
        self.tools: Dict[str, MCPToolMetadata] = {}
        self._load_default_registry()

    def get_tool(self, name: str) -> Optional[MCPToolMetadata]:
        """Retrieve tool metadata by identifier."""
        return self.tools.get(name.lower())

    def get_tools_by_category(self, category: str) -> List[MCPToolMetadata]:
        """Retrieve all tools belonging to a specific capability category."""
        return [t for t in self.tools.values() if t.category.lower() == category.lower()]

    def is_live_capable(self, name: str, env_dict: dict) -> bool:
        """Check if all required env vars are present to run a tool in live mode."""
        tool = self.get_tool(name)
        if not tool:
            return False
        if not tool.required_env_vars:
            return False
        return all(env_dict.get(var) for var in tool.required_env_vars)

    def _load_default_registry(self) -> None:
        """Populate the registry with real, genuinely wireable tools only."""

        self.tools["lakera_guard"] = MCPToolMetadata(
            name="lakera_guard",
            display_name="Lakera Guard",
            category="AI Security",
            description="Real-time prompt injection, jailbreak, and PII guardrail proxy. Used live in the Protect phase's Guardrail Proxy stage.",
            capabilities=["screen_input", "screen_output"],
            endpoints={"screen": "/v2/guard"},
            required_env_vars=["LAKERA_API_KEY"],
            integration_type="hosted_api",
            docs_url="https://platform.lakera.ai/docs",
        )

        self.tools["garak"] = MCPToolMetadata(
            name="garak",
            display_name="Garak",
            category="AI Security",
            description="Open-source LLM vulnerability scanner (NVIDIA-affiliated). Self-hosted — you run it and point us at your runner's URL, there's no public vendor API.",
            capabilities=["execute_scan"],
            endpoints={"trigger_scan": "/run"},
            required_env_vars=["GARAK_RUNNER_URL"],
            integration_type="self_hosted_runner",
            docs_url="https://github.com/NVIDIA/garak",
        )

        self.tools["pyrit"] = MCPToolMetadata(
            name="pyrit",
            display_name="PyRIT",
            category="AI Security",
            description="Microsoft's Python Risk Identification Toolkit for automated multi-turn red-teaming. Self-hosted — same as Garak, configure your own runner's URL.",
            capabilities=["execute_scan"],
            endpoints={"trigger_campaign": "/campaign"},
            required_env_vars=["PYRIT_RUNNER_URL"],
            integration_type="self_hosted_runner",
            docs_url="https://github.com/Azure/PyRIT",
        )

        # ── Remediation / ticketing (real hosted vendor APIs) ─────────────────
        self.tools["jira"] = MCPToolMetadata(
            name="jira",
            display_name="Jira",
            category="Remediation",
            description="Atlassian workflow management and issue tracking. Used for real ticket creation in each phase's final-stage remediation workflow.",
            capabilities=["write_ticket", "get_ticket"],
            endpoints={"create_issue": "/rest/api/2/issue"},
            required_env_vars=["JIRA_URL", "JIRA_USERNAME", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY"],
            integration_type="hosted_api",
            docs_url="https://developer.atlassian.com/cloud/jira/platform/rest/v2/api-group-issues/#api-rest-api-2-issue-post",
        )

        self.tools["servicenow"] = MCPToolMetadata(
            name="servicenow",
            display_name="ServiceNow",
            category="Remediation",
            description="Enterprise IT service management and incident tracking. Used for real incident creation in each phase's final-stage remediation workflow.",
            capabilities=["write_ticket", "get_ticket"],
            endpoints={"create_incident": "/api/now/table/incident"},
            required_env_vars=["SERVICENOW_INSTANCE", "SERVICENOW_USERNAME", "SERVICENOW_PASSWORD"],
            integration_type="hosted_api",
            docs_url="https://docs.servicenow.com/bundle/latest-release-notes/page/integrate/inbound-rest/concept/c_TableAPI.html",
        )

        # ── Live demo targets (real infra we built and control) ──────────────
        # Unlike the 5 tools above, these three are live-only — no mock
        # fallback branch. See AGENTS.md's live-demo notes for why: this is
        # the real control-plane thread (Govern..Recover) for the
        # meridian-support-agent demo target, and a fabricated fallback here
        # would defeat the entire point of that thread being real.

        self.tools["github"] = MCPToolMetadata(
            name="github",
            display_name="GitHub",
            category="AI Security",
            description="Real GitHub REST API access to the meridian-support-agent target repo: discovery (tree, dependency manifest, policy file), Dependabot/Secret Scanning alerts, Actions workflow runs, branch protection, collaborators, and containment/recovery actions (revoke collaborator, disable/enable workflow, revert commit).",
            capabilities=["discover_assets", "get_findings", "get_policy", "enforce_control", "quarantine_asset", "roll_back_release", "retrieve_evidence"],
            endpoints={"api": "https://api.github.com"},
            required_env_vars=["GITHUB_TOKEN", "GITHUB_TARGET_REPO"],
            integration_type="hosted_api",
            docs_url="https://docs.github.com/en/rest",
        )

        self.tools["target_agent"] = MCPToolMetadata(
            name="target_agent",
            display_name="Meridian Support Agent (target)",
            category="AI Security",
            description="The real, deployed meridian-support-agent demo target — a live chat call for Detect's adversarial test, and real /admin/disable /admin/enable calls for Respond/Recover.",
            capabilities=["execute_scan", "quarantine_asset", "roll_back_release"],
            endpoints={"chat": "/chat", "disable": "/admin/disable", "enable": "/admin/enable"},
            required_env_vars=["TARGET_AGENT_URL", "TARGET_AGENT_ADMIN_TOKEN"],
            integration_type="hosted_api",
            docs_url="https://github.com/vaibs2108/meridian-support-agent",
        )

        # ── Data pipeline (bring-your-own — no real vendor to point at yet) ───
        # Unlike every tool above, this isn't a specific named product: it's
        # an honest, generic slot for whatever real SIEM / log / telemetry
        # source a user actually has (Splunk, Sentinel, Elastic, an internal
        # events API — anything with a URL and a key). Same honesty rule as
        # everywhere else in this registry still applies: it reports Mock
        # Fallback until real SIEM_API_URL/SIEM_API_KEY are configured, and
        # MCPClient.external_source_fetch_events() makes a real HTTP call
        # once they are — never a fabricated "connected" result.
        self.tools["external_source"] = MCPToolMetadata(
            name="external_source",
            display_name="External Source (SIEM / API)",
            category="Data Pipeline",
            description="Bring your own SIEM, log platform, or security events API. Connect it here once you have "
                         "one and its real events enrich whichever stage's Data Source Provider you select "
                         "\"+ External Source\" on — not a specific vendor, a generic real connector slot.",
            capabilities=["get_findings"],
            endpoints={"events": "<your configured SIEM_API_URL>"},
            required_env_vars=["SIEM_API_URL", "SIEM_API_KEY"],
            integration_type="hosted_api",
            docs_url="",
        )

        self.tools["slack"] = MCPToolMetadata(
            name="slack",
            display_name="Slack",
            category="Remediation",
            description="Real Slack Bot posting an interactive Approve/Reject message for Respond's human-approval mode; a real person's click calls back to POST /api/slack/interactions.",
            capabilities=["require_approval"],
            endpoints={"post_message": "/chat.postMessage"},
            required_env_vars=["SLACK_BOT_TOKEN", "SLACK_SIGNING_SECRET", "SLACK_CHANNEL_ID"],
            integration_type="hosted_api",
            docs_url="https://api.slack.com/apps",
        )
