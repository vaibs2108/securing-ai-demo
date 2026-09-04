"""
Securing AI — pure-data content for the React frontend.
Consolidates what used to be scattered inline across the 5 Streamlit phase
page files (identify.py, protect.py, ...) into one data-driven config so a
single generic frontend PhaseWorkspace component can render all 14 stages,
instead of hand-porting 5 near-duplicate page files.
"""

from __future__ import annotations

from typing import Any, Dict

# ── Per-phase executive overview card content (mirrors
#    lifecycle_stage.render_usecase_overview_card's inline `details` dict) ──

USE_CASE_OVERVIEW: Dict[str, Dict[str, Any]] = {
    "identify": {
        "title": "🔎 Identify — AI/Agent Asset & Risk Discovery",
        "subtitle": "Shadow AI Discovery · Model & Data Lineage · Agent Risk Scoring",
        "goal": "Establish full visibility into every AI agent, copilot, and model running across the org — sanctioned or shadow. Trace each model's data lineage to classify sensitivity, and compose a composite risk score per agent so Protect/Detect/Respond can prioritize where guardrails matter most.",
        "frameworks": ["NIST AI RMF 1.0", "MITRE ATLAS", "OWASP LLM Top 10", "ISO/IEC 42001"],
        "color": "#00d4ff",
    },
    "protect": {
        "title": "🛡️ Protect — Guardrails, Least Privilege & Secrets",
        "subtitle": "Guardrail Proxy · Least-Privilege Tool Access · Secrets Isolation · Policy-as-Code",
        "goal": "Enforce real-time guardrails against prompt injection, jailbreaks, PII exposure, and toxic content. Audit every agent's tool permissions to least privilege, isolate secrets reachable by LLM context, and codify the results into versioned, enforceable policy-as-code.",
        "frameworks": ["NIST AI RMF 1.0 (Govern/Manage)", "OWASP LLM Top 10", "NIST SP 800-53 r5"],
        "color": "#00ff88",
    },
    "detect": {
        "title": "🚨 Detect — Live Detection & Automated Red-Teaming",
        "subtitle": "Jailbreak/Injection Detection · Behaviour Anomaly Monitoring · Garak/PyRIT Red-Teaming",
        "goal": "Continuously test detection efficacy against a live adversarial prompt corpus, monitor agent behaviour telemetry for anomalies, and run automated red-team campaigns (Garak/PyRIT-style) to surface bypasses before real attackers do.",
        "frameworks": ["MITRE ATLAS", "OWASP LLM Top 10", "NIST AI RMF 1.0 (Measure)"],
        "color": "#ff4444",
    },
    "respond": {
        "title": "🚑 Respond — Containment & Incident Playbooks",
        "subtitle": "Automated Agent Containment · SOAR-Style Incident Playbooks",
        "goal": "Automatically contain a flagged agent — isolate, revoke keys, disable tools, or rate-limit — with HITL approval on high-risk actions, then run the incident through a named SOAR playbook end to end.",
        "frameworks": ["NIST CSF 2.0 (Respond)", "NIST AI RMF 1.0 (Manage)"],
        "color": "#a855f7",
    },
    "recover": {
        "title": "♻️ Recover — Rollback & Guardrail Update Loop",
        "subtitle": "Config/Prompt Rollback · Retraining & Guardrail-Update Loop",
        "goal": "Roll back a compromised agent's prompt template, guardrail policy, or model config to the last known-good snapshot, then feed red-team and incident findings back into guardrail policy updates — closing the loop with measured effectiveness deltas.",
        "frameworks": ["NIST CSF 2.0 (Recover)", "NIST AI RMF 1.0 (Manage)"],
        "color": "#14b8a6",
    },
    "govern": {
        "title": "🏛️ Govern — Policy Authored Once, Applied Everywhere",
        "subtitle": "Policy Catalog & Traceability · Real-Time Compliance Evaluation",
        "goal": "Author policy once as real, versioned code — then apply it everywhere: evaluate every real policy rule's condition against real live findings from Identify, Protect, and Detect, and issue a real compliance decision (Compliant / Blocked / Human Approval Required / Remediation Required) with cited evidence for each.",
        "frameworks": ["NIST AI RMF 1.0 (Govern)", "NIST CSF 2.0 (Govern)", "ISO/IEC 42001"],
        "color": "#f5b700",
    },
}

USE_CASE_COLOURS = {uc: v["color"] for uc, v in USE_CASE_OVERVIEW.items()}
USE_CASE_LABELS = {
    "identify": "🔎 Identify", "protect": "🛡️ Protect", "detect": "🚨 Detect",
    "respond": "🚑 Respond", "recover": "♻️ Recover", "govern": "🏛️ Govern",
}

# ── Per-stage UI configuration: which column drives the category filter,
#    what the secondary result chart shows, and whether a HITL gate applies ──

STAGE_UI_CONFIG: Dict[str, Dict[str, Dict[str, Any]]] = {
    "identify": {
        "shadow_ai_discovery": {
            "filter_column": "agent_type",
            "filter_options": ["LLM Agent", "Copilot", "Chatbot", "Automation Script", "Fine-tuned Model", "RAG Pipeline"],
            "chart": {"dataset": "ai_agent_inventory", "column": "agent_type", "type": "bar", "title": "Agents by Type"},
            "hitl": None,
        },
        "lineage_mapping": {
            "filter_column": "agent_type",
            "filter_options": ["LLM Agent", "Copilot", "Chatbot", "Automation Script", "Fine-tuned Model", "RAG Pipeline"],
            "chart": {"dataset": "model_data_lineage", "column": "data_sensitivity", "type": "donut", "title": "Data Sensitivity Distribution"},
            "hitl": None,
        },
        "risk_scoring": {
            "filter_column": "data_sensitivity",
            "filter_options": ["Public", "Internal", "Confidential", "Regulated-PII"],
            "chart": {"dataset": "agent_risk_register", "column": "blast_radius", "type": "bar", "title": "Blast Radius Distribution"},
            "hitl": {"dataset": "agent_risk_register", "id_column": "agent_id", "label_template": "{agent_id} — risk score {risk_score}, blast radius {blast_radius}", "match_column": "blast_radius", "match_value": "Critical"},
        },
    },
    "protect": {
        "guardrail_proxy": {
            "filter_column": "category",
            "filter_options": ["Prompt Injection", "PII Redaction", "Toxic Content", "Jailbreak", "Off-Topic", "Data Exfiltration"],
            "chart": {"dataset": "guardrail_events", "column": "event_type", "type": "bar", "title": "Guardrail Events by Type"},
            "hitl": {
                "dataset": "guardrail_events",
                "id_column": "event_id",
                "label_template": "{event_id} — {event_type} ({action_taken}): {input_snippet_redacted}",
                "match_column": "event_type",
                "match_value": "credential_exfiltrated",
            },
        },
        "least_privilege": {
            "filter_column": "tool_name",
            "filter_options": [
                "GitHub Deployment PAT (Embedded Secret)",
                "LLM Inference API (Groq Cloud)",
                "Internal Customer Knowledge Base",
                "GitHub Repository Access",
            ],
            "chart": {"dataset": "tool_access_map", "column": "granted_permission", "type": "bar", "title": "Tool Grants by Permission Level"},
            "hitl": {
                "dataset": "tool_access_map",
                "id_column": "mapping_id",
                "label_template": "{mapping_id} — {tool_name}: {granted_permission} (Recommended: {recommended_permission})",
                "match_column": "over_provisioned",
                "match_value": True,
            },
        },
        "secrets_isolation": {
            # Was tool_name/tool_access_map values — same zero-rows bug as
            # least_privilege above, just shifted one stage over. Now matches
            # secrets_exposure_scan (this stage's real input).
            "filter_column": "secret_type",
            "filter_options": ["API Key", "DB Credential", "OAuth Token", "SSH Key", "Webhook Secret"],
            "chart": {"dataset": "secrets_exposure_scan", "column": "isolation_status", "type": "donut", "title": "Secrets Isolation Status"},
            "hitl": {"dataset": "secrets_exposure_scan", "id_column": "secret_id", "label_template": "{secret_id} — {secret_type} in {location}", "match_column": "isolation_status", "match_value": "Exposed"},
        },
        "policy_as_code": {
            "filter_column": "isolation_status",
            "filter_options": ["Isolated", "Exposed", "Remediated"],
            "chart": {"dataset": "guardrail_policies", "column": "enforcement_mode", "type": "bar", "title": "Policy Enforcement Modes"},
            "hitl": None,
        },
    },
    "detect": {
        "injection_detection": {
            "filter_column": "category",
            "filter_options": ["Jailbreak", "Prompt Injection", "Data Exfiltration", "Roleplay Bypass", "Encoding Obfuscation"],
            "chart": {"dataset": "adversarial_prompt_corpus", "column": "category", "type": "bar", "title": "Adversarial Payloads by Category"},
            "hitl": None,
        },
        "behavior_monitoring": {
            # Was category/adversarial-corpus values — same zero-rows bug as
            # protect's two stages above. Now matches agent_behavior_telemetry
            # (this stage's real input, fixed in STAGE_INPUT_OUTPUT_MAP).
            "filter_column": "action_type",
            "filter_options": ["tool_call", "response_generated", "data_access", "external_api_call"],
            "chart": {"dataset": "agent_behavior_telemetry", "column": "action_type", "type": "bar", "title": "Agent Actions by Type"},
            "hitl": None,
        },
        "red_teaming": {
            "filter_column": "action_type",
            "filter_options": ["tool_call", "response_generated", "data_access", "external_api_call"],
            "chart": {"dataset": "redteam_campaign_results", "column": "outcome", "type": "donut", "title": "Red-Team Campaign Outcomes"},
            "hitl": {"dataset": "redteam_campaign_results", "id_column": "test_id", "label_template": "{test_id} — {technique} ({outcome})", "match_column": "outcome", "match_value": "Success"},
        },
    },
    "respond": {
        "containment": {
            "filter_column": "severity",
            "filter_options": ["Critical", "High", "Medium", "Low"],
            "chart": {"dataset": "containment_actions", "column": "action_type", "type": "bar", "title": "Containment Actions by Type"},
            "hitl": {"dataset": "incident_queue", "id_column": "incident_id", "label_template": "{incident_id} — {trigger_source}", "match_column": "severity", "match_value": "Critical"},
        },
        "incident_playbook": {
            "filter_column": "action_type",
            "filter_options": ["Isolate Agent", "Revoke API Key", "Disable Tool Access", "Rate-Limit Agent", "Kill Session"],
            "chart": {"dataset": "soar_playbooks", "column": "playbook_name", "value_column": "success_rate", "type": "bar", "title": "Playbook Success Rate"},
            "hitl": None,
        },
    },
    "recover": {
        "rollback": {
            "filter_column": "snapshot_type",
            "filter_options": ["Prompt Template", "Guardrail Policy", "Model Config", "Tool Permission Set"],
            "chart": {"dataset": "rollback_events", "column": "outcome", "type": "donut", "title": "Rollback Outcomes"},
            "hitl": {"dataset": "config_snapshots", "id_column": "snapshot_id", "label_template": "{snapshot_id} — version {version}, created {created_at}", "match_column": "rollback_available", "match_value": False},
        },
        "guardrail_update": {
            "filter_column": "initiated_by",
            "filter_options": ["Automated", "Analyst"],
            "chart": {"dataset": "guardrail_update_log", "column": "source_finding", "type": "bar", "title": "Guardrail Updates by Source"},
            "hitl": None,
        },
    },
    "govern": {
        "policy_catalog": {
            "filter_column": "enforcement_mode",
            "filter_options": ["Enforced — Block", "Enforced — Human Approval Required", "Enforced — Remediation SLA"],
            "chart": {"dataset": "guardrail_policies", "column": "enforcement_mode", "type": "bar", "title": "Policy Enforcement Modes"},
            "hitl": None,
        },
        "compliance_evaluation": {
            "filter_column": "severity",
            "filter_options": ["critical", "high", "medium", "low"],
            "chart": {"dataset": "governance_compliance_evaluation", "column": "decision", "type": "donut", "title": "Compliance Decisions"},
            "hitl": {"dataset": "governance_compliance_evaluation", "id_column": "rule_id", "label_template": "{rule_id} — {rule_name} ({decision})", "match_column": "triggered", "match_value": True},
        },
    },
}

# ── Which datasets belong to which phase, for the Data Explorer page ──

PHASE_DATASETS: Dict[str, list] = {
    "identify": ["ai_agent_inventory", "model_data_lineage", "agent_risk_register"],
    "protect": ["guardrail_policies", "guardrail_events", "tool_access_map", "secrets_exposure_scan"],
    "detect": ["adversarial_prompt_corpus", "agent_behavior_telemetry", "redteam_campaign_results"],
    "respond": ["incident_queue", "containment_actions", "soar_playbooks"],
    "recover": ["config_snapshots", "rollback_events", "guardrail_update_log"],
    "govern": ["governance_compliance_evaluation"],
}

# ── Agents Repository — 14 agents, names matching agent_manager.AGENT_NAME_MAP exactly ──

AGENTS_DB: Dict[str, Dict[str, Any]] = {
    "identify": {
        "color": "#00d4ff",
        "framework": "NIST AI RMF 1.0, MITRE ATLAS, OWASP LLM Top 10, ISO/IEC 42001",
        "agents": [
            {
                "name": "ShadowAIDiscoveryAgent",
                "stage": "Shadow AI Discovery",
                "role": "Scans Git repos, cloud configs, and network/CASB telemetry to discover every AI agent, copilot, and model running across the org — sanctioned or shadow.",
                "mitre_ref": "AML.T0034 — Discover LLM System Information",
            },
            {
                "name": "LineageMappingAgent",
                "stage": "Model & Data Lineage Mapping",
                "role": "Traces each model's base model, fine-tune dataset, and training-data source to classify data sensitivity and downstream consumers.",
                "mitre_ref": "AML.T0020 — Poison Training Data (surface analysis)",
            },
            {
                "name": "AgentRiskScoringAgent",
                "stage": "Agent Risk Scoring",
                "role": "Composes a 0-100 risk score per agent from permission scope, exposure, data sensitivity, and ownership gaps.",
                "mitre_ref": "N/A — Analytical / Risk Scoring",
            },
        ],
    },
    "protect": {
        "color": "#00ff88",
        "framework": "NIST AI RMF 1.0 (Govern/Manage), OWASP LLM Top 10, NIST SP 800-53 r5",
        "agents": [
            {
                "name": "GuardrailProxyAgent",
                "stage": "Guardrail Proxy",
                "role": "Intercepts every prompt/response through configured policies to filter prompt injection, jailbreaks, PII, and toxic content.",
                "mitre_ref": "AML.T0051 — LLM Prompt Injection (defensive)",
            },
            {
                "name": "LeastPrivilegeAuditAgent",
                "stage": "Least-Privilege Tool Access",
                "role": "Compares every agent's granted tool permissions against a least-privilege baseline to flag over-provisioned access.",
                "mitre_ref": "N/A — Access Control Auditing",
            },
            {
                "name": "SecretsIsolationAgent",
                "stage": "Secrets Isolation",
                "role": "Scans prompt history, code repos, env vars, and chat logs for API keys, credentials, and tokens reachable by an LLM.",
                "mitre_ref": "N/A — Credential Exposure Scanning",
            },
            {
                "name": "PolicyAsCodeAgent",
                "stage": "Policy-as-Code",
                "role": "Codifies guardrail, access, and secrets findings into versioned, enforceable policy-as-code definitions.",
                "mitre_ref": "N/A — Policy Codification",
            },
        ],
    },
    "detect": {
        "color": "#ff4444",
        "framework": "MITRE ATLAS, OWASP LLM Top 10, NIST AI RMF 1.0 (Measure)",
        "agents": [
            {
                "name": "InjectionDetectionAgent",
                "stage": "Live Jailbreak & Injection Detection",
                "role": "Runs a labelled adversarial prompt corpus against live agents to measure real-time jailbreak and injection detection rates.",
                "mitre_ref": "AML.T0051, AML.T0054",
            },
            {
                "name": "BehaviorMonitoringAgent",
                "stage": "Anomalous Agent Behaviour Monitoring",
                "role": "Monitors agent action telemetry — tool calls, data access, external API calls — for statistically anomalous behaviour.",
                "mitre_ref": "AML.T0034",
            },
            {
                "name": "RedTeamOrchestratorAgent",
                "stage": "Automated Red-Teaming",
                "role": "Runs Garak/PyRIT-style automated adversarial campaigns against agents and compiles outcomes into a red-team report.",
                "mitre_ref": "AML.T0048, AML.T0043",
            },
        ],
    },
    "respond": {
        "color": "#a855f7",
        "framework": "NIST CSF 2.0 (Respond), NIST AI RMF 1.0 (Manage)",
        "agents": [
            {
                "name": "ContainmentAgent",
                "stage": "Automated Containment",
                "role": "Automatically contains a flagged agent — isolate, revoke keys, disable tools, or rate-limit — routing high-risk actions through HITL approval.",
                "mitre_ref": "N/A — Containment / Active Defense",
            },
            {
                "name": "SOARPlaybookAgent",
                "stage": "SOAR Incident Playbook",
                "role": "Executes a named SOAR-style incident playbook end to end from trigger condition through resolution.",
                "mitre_ref": "N/A — Incident Response Orchestration",
            },
        ],
    },
    "recover": {
        "color": "#14b8a6",
        "framework": "NIST CSF 2.0 (Recover), NIST AI RMF 1.0 (Manage)",
        "agents": [
            {
                "name": "RollbackAgent",
                "stage": "Config & Prompt Rollback",
                "role": "Reverts an agent's prompt template, guardrail policy, or model config to the last known-good version snapshot.",
                "mitre_ref": "N/A — Recovery / Configuration Management",
            },
            {
                "name": "GuardrailUpdateAgent",
                "stage": "Guardrail Update Loop",
                "role": "Feeds red-team and incident findings back into guardrail policy updates and measures the resulting effectiveness delta.",
                "mitre_ref": "N/A — Closed-Loop Policy Update",
            },
        ],
    },
    "govern": {
        "color": "#f5b700",
        "framework": "NIST AI RMF 1.0 (Govern), NIST CSF 2.0 (Govern), ISO/IEC 42001",
        "agents": [
            {
                "name": "GovernPolicyAgent",
                "stage": "Policy Catalog & Traceability",
                "role": "Reviews the real, authored governance policy fetched from the target repo for ownership, versioning, and compliance-framework traceability.",
                "mitre_ref": "N/A — Policy Governance / Traceability Audit",
            },
            {
                "name": "GovernComplianceAgent",
                "stage": "Real-Time Compliance Evaluation",
                "role": "Evaluates each policy rule's real condition against live Identify/Protect/Detect state and reports the resulting compliance decision with cited evidence.",
                "mitre_ref": "N/A — Continuous Compliance Evaluation",
            },
        ],
    },
}

COPILOT_STARTER_QUESTIONS = [
    "Which agents are Shadow AI?",
    "What's our guardrail block rate this week?",
    "Show the latest red-team campaign results",
    "Which agents are highest risk right now?",
    "Show MITRE ATLAS technique distribution",
    "Which agents had a recent rollback?",
]
