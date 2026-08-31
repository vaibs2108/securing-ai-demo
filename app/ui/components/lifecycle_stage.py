"""
Securing AI — Lifecycle stage data & lookup helpers.
Pure data (STAGE_DEFINITIONS, STAGE_INPUT_OUTPUT_MAP) and lookup functions
shared by the FastAPI backend (backend/main.py). The Streamlit-only rendering
functions that used to live here (render_stage_progress, render_3col_input_panel,
etc.) were removed when the legacy Streamlit UI was retired — React
(frontend/src/pages/PhaseWorkspace.tsx) is the only UI now.
"""

from __future__ import annotations

from typing import Dict, List, Optional


def _get_previous_stage_output(use_case: str, stage_key: str) -> str:
    """Return a human-readable description of what the previous stage produced
    as input for the current stage. Used in the Input & Config panel."""

    prev_output_map = {
        "identify": {
            "lineage_mapping": "Shadow AI Discovery stage produced a full agent/model inventory with sanctioned vs. shadow classification, LLM provider, and data access scope per discovered system.",
            "risk_scoring": "Lineage Mapping stage produced training/fine-tune data lineage chains with data sensitivity classifications and downstream consumer counts per model.",
        },
        "protect": {
            # least_privilege and secrets_isolation each analyse their own
            # dataset (tool_access_map / secrets_exposure_scan respectively)
            # rather than consuming the prior stage's output — see
            # STAGE_INPUT_OUTPUT_MAP above for why. No real handoff exists
            # between guardrail_proxy -> least_privilege or
            # least_privilege -> secrets_isolation, so no entry here for
            # either (the UI section that renders this simply stays hidden).
            "policy_as_code": "Secrets Isolation stage produced a scan of exposed API keys, credentials, and tokens found in prompt history, code repos, and chat logs.",
        },
        "detect": {
            # behavior_monitoring analyses agent_behavior_telemetry directly,
            # not injection_detection's output — see STAGE_INPUT_OUTPUT_MAP.
            "red_teaming": "Behaviour Monitoring stage produced an agent telemetry stream with anomaly scores and flagged baseline deviations per action.",
        },
        "respond": {
            "incident_playbook": "Automated Containment stage produced a log of containment actions (isolate/revoke/disable/rate-limit) with automation and HITL-approval status per action.",
        },
        "recover": {
            "guardrail_update": "Config & Prompt Rollback stage produced a rollback event log with reason, initiator, and outcome per reverted agent configuration.",
        },
    }

    return prev_output_map.get(use_case, {}).get(stage_key, "")


# ── Stage Definitions ───────────────────────────────────────────────────────

STAGE_DEFINITIONS: Dict[str, List[Dict[str, str]]] = {
    "identify": [
        {
            "key": "shadow_ai_discovery",
            "name": "Shadow AI Discovery",
            "icon": "🕵️",
            "description": "Scan configs, repos, and network/CASB telemetry to discover every AI agent, copilot, and model running across the org — sanctioned or shadow.",
            "agent": "ShadowAIDiscoveryAgent",
        },
        {
            "key": "lineage_mapping",
            "name": "Model & Data Lineage Mapping",
            "icon": "🧬",
            "description": "Trace each model's base model, fine-tune dataset, and training-data source to classify data sensitivity and downstream blast radius.",
            "agent": "LineageMappingAgent",
        },
        {
            "key": "risk_scoring",
            "name": "Agent Risk Scoring",
            "icon": "📊",
            "description": "Compute a composite risk score per agent from permission scope, exposure, data sensitivity, and ownership gaps.",
            "agent": "AgentRiskScoringAgent",
        },
    ],
    "protect": [
        {
            "key": "guardrail_proxy",
            "name": "Guardrail Proxy",
            "icon": "🛡️",
            "description": "Intercept every prompt/response through a guardrail proxy that filters prompt injection, jailbreaks, PII, and toxic content in real time.",
            "agent": "GuardrailProxyAgent",
        },
        {
            "key": "least_privilege",
            "name": "Least-Privilege Tool Access",
            "icon": "🔑",
            "description": "Audit every agent's tool permissions against a least-privilege baseline and flag over-provisioned access.",
            "agent": "LeastPrivilegeAuditAgent",
        },
        {
            "key": "secrets_isolation",
            "name": "Secrets Isolation",
            "icon": "🔒",
            "description": "Scan prompts, repos, and chat logs for exposed API keys, credentials, and tokens reachable by an LLM.",
            "agent": "SecretsIsolationAgent",
        },
        {
            "key": "policy_as_code",
            "name": "Policy-as-Code",
            "icon": "📜",
            "description": "Codify guardrail, access, and secrets findings into versioned, enforceable policy-as-code definitions.",
            "agent": "PolicyAsCodeAgent",
        },
    ],
    "detect": [
        {
            "key": "injection_detection",
            "name": "Live Jailbreak & Injection Detection",
            "icon": "🚨",
            "description": "Run an adversarial prompt corpus against live agents to measure real-time jailbreak and prompt-injection detection rates.",
            "agent": "InjectionDetectionAgent",
        },
        {
            "key": "behavior_monitoring",
            "name": "Anomalous Agent Behaviour Monitoring",
            "icon": "📡",
            "description": "Monitor agent action telemetry (tool calls, data access, external API calls) for statistically anomalous behaviour.",
            "agent": "BehaviorMonitoringAgent",
        },
        {
            "key": "red_teaming",
            "name": "Automated Red-Teaming",
            "icon": "⚔️",
            "description": "Run Garak/PyRIT-style automated adversarial campaigns against agents and compile a red-team findings report.",
            "agent": "RedTeamOrchestratorAgent",
        },
    ],
    "respond": [
        {
            "key": "containment",
            "name": "Automated Containment",
            "icon": "🧯",
            "description": "Automatically contain a flagged agent — isolate, revoke keys, disable tools, or rate-limit — with HITL approval where required.",
            "agent": "ContainmentAgent",
        },
        {
            "key": "incident_playbook",
            "name": "SOAR Incident Playbook",
            "icon": "📋",
            "description": "Execute a SOAR-style incident playbook end to end, from trigger condition through resolution.",
            "agent": "SOARPlaybookAgent",
        },
    ],
    "recover": [
        {
            "key": "rollback",
            "name": "Config & Prompt Rollback",
            "icon": "⏪",
            "description": "Roll back an agent's prompt template, guardrail policy, or model config to the last known-good version snapshot.",
            "agent": "RollbackAgent",
        },
        {
            "key": "guardrail_update",
            "name": "Guardrail Update Loop",
            "icon": "🔁",
            "description": "Feed red-team and incident findings back into guardrail policy updates, closing the loop with measured effectiveness deltas.",
            "agent": "GuardrailUpdateAgent",
        },
    ],
}


# ── Input & Output Dataset Mapping ──────────────────────────────────────────

STAGE_INPUT_OUTPUT_MAP = {
    "identify": {
        "shadow_ai_discovery": {
            # No separate "raw scan feed" dataset exists — this stage's real
            # subject is the agent inventory itself, reviewed before vs after
            # AI classification. See AGENTS.md Section 28's stage-mapping note.
            "input_key": "ai_agent_inventory",
            "input_name": "AI Agent & Model Inventory (Unclassified)",
            "input_desc": "Every AI agent, copilot, and model surfaced by Git repo scans, cloud config exports, and network/CASB traffic — not yet reviewed for sanctioned-vs-shadow status.",
            "output_key": "ai_agent_inventory",
            "output_name": "AI Agent & Model Inventory (Reviewed)",
            "output_desc": "The same roster after AI review — sanctioned-vs-shadow classification and LLM provider confirmed per agent.",
        },
        "lineage_mapping": {
            "input_key": "ai_agent_inventory",
            "input_name": "AI Agent & Model Inventory",
            "input_desc": "Discovered agents and models from the Shadow AI Discovery stage.",
            "output_key": "model_data_lineage",
            "output_name": "Model & Data Lineage Map",
            "output_desc": "Base model, fine-tune dataset, training data source, and data-sensitivity classification per model.",
        },
        "risk_scoring": {
            "input_key": "model_data_lineage",
            "input_name": "Model & Data Lineage Map",
            "input_desc": "Lineage chains and data sensitivity classifications ready for risk composition.",
            "output_key": "agent_risk_register",
            "output_name": "Agent Risk Register",
            "output_desc": "Composite 0-100 risk score per agent with contributing risk factors and blast radius rating.",
        },
    },
    "protect": {
        "guardrail_proxy": {
            "input_key": "guardrail_policies",
            "input_name": "Guardrail Policy Library",
            "input_desc": "Configured prompt-injection, PII, jailbreak, and toxicity policies awaiting live enforcement.",
            "output_key": "guardrail_events",
            "output_name": "Guardrail Proxy Event Stream",
            "output_desc": "Live stream of blocked, redacted, and flagged prompt/response events with policy attribution.",
        },
        "least_privilege": {
            # Was wrongly wired to guardrail_events (a content-filtering
            # log — zero permission columns). Tool grants only exist in
            # tool_access_map, so — like shadow_ai_discovery above — this is
            # a before/after-AI-review pairing on the same dataset.
            "input_key": "tool_access_map",
            "input_name": "Tool Permission Map (Unaudited)",
            "input_desc": "Granted vs. recommended permission per agent/tool pairing, awaiting least-privilege compliance audit.",
            "output_key": "tool_access_map",
            "output_name": "Tool Permission Map (Audited)",
            "output_desc": "The same mappings with over-provisioning flags confirmed by AI audit.",
        },
        "secrets_isolation": {
            # Was wrongly wired to tool_access_map (permission grants — zero
            # credential columns). Same before/after-AI-review pairing as
            # least_privilege above, this time on secrets_exposure_scan.
            "input_key": "secrets_exposure_scan",
            "input_name": "Secrets Exposure Scan (Unremediated)",
            "input_desc": "API keys, credentials, and tokens found exposed to LLM context, awaiting isolation/remediation review.",
            "output_key": "secrets_exposure_scan",
            "output_name": "Secrets Exposure Scan (Reviewed)",
            "output_desc": "The same findings with isolation status and remediation guidance confirmed by AI review.",
        },
        "policy_as_code": {
            "input_key": "secrets_exposure_scan",
            "input_name": "Secrets Exposure Scan",
            "input_desc": "Exposure findings ready for codification into enforceable policy.",
            "output_key": "guardrail_policies",
            "output_name": "Policy-as-Code Package",
            "output_desc": "Versioned, enforceable policy definitions compiled from guardrail, access, and secrets findings.",
        },
    },
    "detect": {
        "injection_detection": {
            # Before/after-AI-review pairing, same rationale as
            # identify/shadow_ai_discovery above.
            "input_key": "adversarial_prompt_corpus",
            "input_name": "Adversarial Prompt Corpus (Unlabelled)",
            "input_desc": "Canned jailbreak, injection, and exfiltration payloads mapped to OWASP LLM Top 10 / MITRE ATLAS, awaiting AI-reviewed detection scoring.",
            "output_key": "adversarial_prompt_corpus",
            "output_name": "Adversarial Prompt Corpus (Scored)",
            "output_desc": "The same corpus with per-payload detection outcome and confidence score confirmed by AI review.",
        },
        "behavior_monitoring": {
            # Was wrongly wired to adversarial_prompt_corpus (canned jailbreak
            # payloads — unrelated to agent action telemetry). Real subject
            # only exists as agent_behavior_telemetry itself; same
            # before/after-AI-review pairing as the other bootstrap stages.
            "input_key": "agent_behavior_telemetry",
            "input_name": "Agent Behaviour Telemetry (Raw)",
            "input_desc": "Per-action telemetry (tool calls, data access, API calls) with anomaly scores, awaiting AI review for statistically anomalous patterns.",
            "output_key": "agent_behavior_telemetry",
            "output_name": "Agent Behaviour Telemetry (Reviewed)",
            "output_desc": "The same telemetry with anomalous agents and baseline-deviation patterns confirmed by AI review.",
        },
        "red_teaming": {
            "input_key": "agent_behavior_telemetry",
            "input_name": "Agent Behaviour Telemetry",
            "input_desc": "Anomalous behaviour patterns feeding red-team campaign targeting.",
            "output_key": "redteam_campaign_results",
            "output_name": "Red-Team Campaign Report",
            "output_desc": "Garak/PyRIT-style automated attack outcomes (Success/Blocked/Partial) with remediation recommendations.",
        },
    },
    "respond": {
        "containment": {
            "input_key": "incident_queue",
            "input_name": "Security Incident Queue",
            "input_desc": "Open incidents triggered by guardrail events, red-team findings, or behaviour anomalies.",
            "output_key": "containment_actions",
            "output_name": "Containment Action Log",
            "output_desc": "Isolate/revoke/disable/rate-limit actions taken per incident, with automation and HITL-approval status.",
        },
        "incident_playbook": {
            "input_key": "containment_actions",
            "input_name": "Containment Action Log",
            "input_desc": "Completed containment actions ready for full playbook execution.",
            "output_key": "soar_playbooks",
            "output_name": "SOAR Playbook Execution Package",
            "output_desc": "Named incident playbooks with ordered steps, execution time, and success rate.",
        },
    },
    "recover": {
        "rollback": {
            "input_key": "config_snapshots",
            "input_name": "Config Version Snapshots",
            "input_desc": "Versioned prompt template, guardrail policy, and model config snapshots eligible for rollback.",
            "output_key": "rollback_events",
            "output_name": "Rollback Event Log",
            "output_desc": "Executed rollbacks with source/target version, reason, initiator, and outcome.",
        },
        "guardrail_update": {
            "input_key": "rollback_events",
            "input_name": "Rollback Event Log",
            "input_desc": "Rollback outcomes and root-cause reasons feeding the guardrail update loop.",
            "output_key": "guardrail_update_log",
            "output_name": "Guardrail Update Log",
            "output_desc": "Policy updates deployed from red-team/incident findings, with before/after block-rate effectiveness.",
        },
    },
}


# ── Public API ───────────────────────────────────────────────────────────────

def get_stages_for_usecase(use_case: str) -> List[Dict[str, str]]:
    """Return the ordered list of stage definitions for a use case."""
    return STAGE_DEFINITIONS.get(use_case, [])

def get_dataset_name_for_stage(use_case: str, stage_key: str) -> str:
    mappings = {
        "identify": {
            "shadow_ai_discovery": "AI Agent & Model Inventory (300 discovered systems)",
            "lineage_mapping": "Model & Data Lineage Records (~165 models)",
            "risk_scoring": "Agent Risk Register (300 scored agents)",
        },
        "protect": {
            "guardrail_proxy": "Guardrail Proxy Events (800 intercepted prompts)",
            "least_privilege": "Tool Permission Map (250 agent/tool pairs)",
            "secrets_isolation": "Secrets Exposure Scan (60 credential findings)",
            "policy_as_code": "Guardrail Policy Library (40 codified policies)",
        },
        "detect": {
            "injection_detection": "Adversarial Prompt Corpus (500 payloads)",
            "behavior_monitoring": "Agent Behaviour Telemetry (2,000 events)",
            "red_teaming": "Red-Team Campaign Results (200 automated tests)",
        },
        "respond": {
            "containment": "Security Incident Queue (80 open incidents)",
            "incident_playbook": "SOAR Playbook Library (15 playbooks)",
        },
        "recover": {
            "rollback": "Config Version Snapshots (100 versions)",
            "guardrail_update": "Guardrail Update Log (60 policy updates)",
        },
    }
    return mappings.get(use_case, {}).get(stage_key, "Security Event Telemetry")


def get_agent_details_for_stage(use_case: str, stage_key: str) -> dict:
    mappings = {
        "identify": {
            "shadow_ai_discovery": {
                "agent": "ShadowAIDiscoveryAgent",
                "analysis": "Scans Git repos, cloud configs, CASB/network traffic, and survey responses to enumerate every AI agent and model in use, sanctioned or not.",
                "output": "Full agent/model inventory with sanctioned-vs-shadow classification, LLM provider, and internet-facing exposure."
            },
            "lineage_mapping": {
                "agent": "LineageMappingAgent",
                "analysis": "Traces each model's base model, fine-tune dataset, and training-data source to classify data sensitivity and downstream consumers.",
                "output": "Model-to-data lineage chains with sensitivity classification and downstream consumer counts."
            },
            "risk_scoring": {
                "agent": "AgentRiskScoringAgent",
                "analysis": "Composes a risk score from permission scope, exposure, data sensitivity, and ownership gaps for every discovered agent.",
                "output": "0-100 agent risk register with contributing risk factors and blast-radius rating."
            },
        },
        "protect": {
            "guardrail_proxy": {
                "agent": "GuardrailProxyAgent",
                "analysis": "Intercepts every prompt and response through configured policies to filter prompt injection, jailbreaks, PII, and toxic content.",
                "output": "Live enforcement event stream — blocked, redacted, and flagged interactions with policy attribution."
            },
            "least_privilege": {
                "agent": "LeastPrivilegeAuditAgent",
                "analysis": "Compares every agent's granted tool permissions against a least-privilege baseline to flag over-provisioned access.",
                "output": "Tool permission map with over-provisioning flags and recommended permission downgrades."
            },
            "secrets_isolation": {
                "agent": "SecretsIsolationAgent",
                "analysis": "Scans prompt history, code repos, env vars, and chat logs for API keys, credentials, and tokens reachable by an LLM.",
                "output": "Secrets exposure scan with isolation status per finding."
            },
            "policy_as_code": {
                "agent": "PolicyAsCodeAgent",
                "analysis": "Codifies guardrail, access, and secrets findings into versioned, enforceable policy-as-code definitions.",
                "output": "Deployable policy-as-code package ready for CI/CD-gated rollout."
            },
        },
        "detect": {
            "injection_detection": {
                "agent": "InjectionDetectionAgent",
                "analysis": "Runs a labelled adversarial prompt corpus against live agents to measure real-time jailbreak and injection detection rates.",
                "output": "Per-payload detection outcome and confidence score mapped to MITRE ATLAS techniques."
            },
            "behavior_monitoring": {
                "agent": "BehaviorMonitoringAgent",
                "analysis": "Monitors agent action telemetry — tool calls, data access, external API calls — for statistically anomalous behaviour.",
                "output": "Anomaly-scored behaviour telemetry with flagged baseline deviations."
            },
            "red_teaming": {
                "agent": "RedTeamOrchestratorAgent",
                "analysis": "Runs Garak/PyRIT-style automated adversarial campaigns against agents and compiles outcomes into a red-team report.",
                "output": "Red-team campaign results (Success/Blocked/Partial) with remediation recommendations."
            },
        },
        "respond": {
            "containment": {
                "agent": "ContainmentAgent",
                "analysis": "Automatically contains a flagged agent — isolate, revoke keys, disable tools, or rate-limit — routing high-risk actions through HITL approval.",
                "output": "Containment action log with automation and HITL-approval status per incident."
            },
            "incident_playbook": {
                "agent": "SOARPlaybookAgent",
                "analysis": "Executes a named SOAR-style incident playbook end to end from trigger condition through resolution.",
                "output": "Playbook execution record with step timing and success outcome."
            },
        },
        "recover": {
            "rollback": {
                "agent": "RollbackAgent",
                "analysis": "Reverts an agent's prompt template, guardrail policy, or model config to the last known-good version snapshot.",
                "output": "Rollback event log with source/target version, reason, and outcome."
            },
            "guardrail_update": {
                "agent": "GuardrailUpdateAgent",
                "analysis": "Feeds red-team and incident findings back into guardrail policy updates and measures the resulting effectiveness delta.",
                "output": "Deployed guardrail policy updates with before/after block-rate improvement."
            },
        },
    }
    return mappings.get(use_case, {}).get(stage_key, {
        "agent": "SecurityAgent",
        "analysis": "Analyzes ingested security data against known attack rules.",
        "output": "Findings and remediation advice."
    })
