"""
KPIEngine — Computes all 20 AI security metrics and the AI Security Posture Index.
"""
from __future__ import annotations

import logging
from typing import Dict, Any
import pandas as pd

logger = logging.getLogger(__name__)


class KPIEngine:
    """Computes all 20 security and execution KPIs dynamically from datasets.
    
    Includes the overall weighted AI Readiness Index.
    """

    def __init__(self, datasets: Dict[str, pd.DataFrame]) -> None:
        self.datasets = datasets
        self.kpis: Dict[str, float] = {}
        self.compute_all()

    def compute_all(self) -> Dict[str, float]:
        """Compute all 20 KPIs from the provided datasets."""
        # ── 1. Identify KPIs ─────────────────────────────────────────────────
        agents = self.datasets.get("ai_agent_inventory")
        lineage = self.datasets.get("model_data_lineage")
        risk_reg = self.datasets.get("agent_risk_register")

        # Shadow AI Discovery Rate: % agents classified Shadow AI
        if agents is not None and not agents.empty:
            shadow_rate = (agents["sanctioned_status"] == "Shadow AI").sum() / len(agents) * 100
        else:
            shadow_rate = 18.5
        self.kpis["Shadow AI Discovery Rate"] = round(shadow_rate, 1)

        # High-Risk Agent Rate: % agents rated High or Critical blast radius
        if risk_reg is not None and not risk_reg.empty:
            high_risk = risk_reg["blast_radius"].isin(["High", "Critical"]).sum() / len(risk_reg) * 100
        else:
            high_risk = 22.0
        self.kpis["High-Risk Agent Rate"] = round(high_risk, 1)

        # Lineage Coverage Rate: % of agents with a traced lineage record
        if agents is not None and not agents.empty and lineage is not None:
            lineage_coverage = min(100.0, (len(lineage) / len(agents)) * 100) if len(agents) > 0 else 68.0
        else:
            lineage_coverage = 68.0
        self.kpis["Lineage Coverage Rate"] = round(lineage_coverage, 1)

        # Avg Agent Risk Score: mean composite risk score
        if risk_reg is not None and not risk_reg.empty:
            avg_risk = risk_reg["risk_score"].mean()
        else:
            avg_risk = 42.0
        self.kpis["Avg Agent Risk Score"] = round(avg_risk, 1)

        # ── 2. Protect KPIs ──────────────────────────────────────────────────
        policies = self.datasets.get("guardrail_policies")
        events = self.datasets.get("guardrail_events")
        tool_access = self.datasets.get("tool_access_map")
        secrets = self.datasets.get("secrets_exposure_scan")

        # Guardrail Block Rate: % enforcement events resulting in Blocked
        if events is not None and not events.empty:
            block_rate = (events["action_taken"] == "Blocked").sum() / len(events) * 100
        else:
            block_rate = 91.0
        self.kpis["Guardrail Block Rate"] = round(block_rate, 1)

        # Least-Privilege Compliance Rate: % tool grants NOT over-provisioned
        if tool_access is not None and not tool_access.empty:
            compliance = (~tool_access["over_provisioned"]).sum() / len(tool_access) * 100
        else:
            compliance = 76.0
        self.kpis["Least-Privilege Compliance Rate"] = round(compliance, 1)

        # Secrets Isolation Rate: % secrets Isolated or Remediated
        if secrets is not None and not secrets.empty:
            isolated = secrets["isolation_status"].isin(["Isolated", "Remediated"]).sum() / len(secrets) * 100
        else:
            isolated = 82.0
        self.kpis["Secrets Isolation Rate"] = round(isolated, 1)

        # PII Redaction Rate: % PII-Detected events that were Redacted or Blocked
        if events is not None and not events.empty:
            pii_events = events[events["event_type"] == "PII Detected"]
            if not pii_events.empty:
                pii_rate = pii_events["action_taken"].isin(["Redacted", "Blocked"]).sum() / len(pii_events) * 100
            else:
                pii_rate = 95.0
        else:
            pii_rate = 95.0
        self.kpis["PII Redaction Rate"] = round(pii_rate, 1)

        # ── 3. Detect KPIs ───────────────────────────────────────────────────
        adversarial = self.datasets.get("adversarial_prompt_corpus")
        behavior = self.datasets.get("agent_behavior_telemetry")
        redteam = self.datasets.get("redteam_campaign_results")
        # Fetched here (not in the Respond section below, though it's also
        # used there) because MTTD needs it first.
        incidents = self.datasets.get("incident_queue")

        # Jailbreak Detection Rate: % adversarial payloads detected
        if adversarial is not None and not adversarial.empty:
            jailbreak_rate = adversarial["detected"].sum() / len(adversarial) * 100
        else:
            jailbreak_rate = 82.0
        self.kpis["Jailbreak Detection Rate"] = round(jailbreak_rate, 1)

        # Red-Team Attack Success Rate: % campaigns that succeeded (lower is better)
        if redteam is not None and not redteam.empty:
            attack_success = (redteam["outcome"] == "Success").sum() / len(redteam) * 100
        else:
            attack_success = 22.0
        self.kpis["Red-Team Attack Success Rate"] = round(attack_success, 1)

        # MTTD: Mean time to detect (hours) — real delta between when each
        # incident's underlying event occurred and when it was detected.
        if incidents is not None and not incidents.empty and {"occurred_at", "detected_at"}.issubset(incidents.columns):
            occurred = pd.to_datetime(incidents["occurred_at"])
            detected = pd.to_datetime(incidents["detected_at"])
            mttd_hours = (detected - occurred).dt.total_seconds().mean() / 3600
        else:
            mttd_hours = 1.6
        self.kpis["MTTD"] = round(mttd_hours, 1)

        # Anomaly Detection Coverage: % agents with behavior telemetry monitored
        if behavior is not None and not behavior.empty and agents is not None and not agents.empty:
            monitored = behavior["agent_id"].nunique()
            anomaly_cov = min(100.0, (monitored / agents["agent_id"].nunique()) * 100) if agents["agent_id"].nunique() > 0 else 88.0
        else:
            anomaly_cov = 88.0
        self.kpis["Anomaly Detection Coverage"] = round(anomaly_cov, 1)

        # ── 4. Respond KPIs ──────────────────────────────────────────────────
        # incidents fetched earlier, in the Detect section (MTTD needs it first)
        containment = self.datasets.get("containment_actions")
        playbooks = self.datasets.get("soar_playbooks")

        # Automated Containment Rate: % containment actions fully automated
        if containment is not None and not containment.empty:
            auto_rate = containment["automated"].sum() / len(containment) * 100
        else:
            auto_rate = 70.0
        self.kpis["Automated Containment Rate"] = round(auto_rate, 1)

        # MTTC: Mean time to contain (hours) — real delta between each
        # containment action's timestamp and the incident it responded to.
        if (
            containment is not None and not containment.empty
            and incidents is not None and not incidents.empty
            and "incident_id" in containment.columns and "detected_at" in incidents.columns
        ):
            merged = containment.merge(incidents[["incident_id", "detected_at"]], on="incident_id", how="inner")
            if not merged.empty:
                detected = pd.to_datetime(merged["detected_at"])
                contained = pd.to_datetime(merged["timestamp"])
                deltas_hours = (contained - detected).dt.total_seconds() / 3600
                deltas_hours = deltas_hours[deltas_hours >= 0]
                mttc_hours = deltas_hours.mean() if not deltas_hours.empty else 1.2
            else:
                mttc_hours = 1.2
        else:
            mttc_hours = 1.2
        self.kpis["MTTC"] = round(mttc_hours, 1)

        # Playbook Success Rate: avg success_rate across playbooks
        if playbooks is not None and not playbooks.empty:
            playbook_success = playbooks["success_rate"].mean()
        else:
            playbook_success = 93.0
        self.kpis["Playbook Success Rate"] = round(playbook_success, 1)

        # HITL Approval Rate: % containment actions with HITL approval
        if containment is not None and not containment.empty:
            hitl_rate = containment["hitl_approved"].sum() / len(containment) * 100
        else:
            hitl_rate = 89.0
        self.kpis["HITL Approval Rate"] = round(hitl_rate, 1)

        # ── 5. Recover KPIs ──────────────────────────────────────────────────
        snapshots = self.datasets.get("config_snapshots")
        rollbacks = self.datasets.get("rollback_events")
        updates = self.datasets.get("guardrail_update_log")

        # Rollback Success Rate: % rollback events with outcome=Success
        if rollbacks is not None and not rollbacks.empty:
            rollback_success = (rollbacks["outcome"] == "Success").sum() / len(rollbacks) * 100
        else:
            rollback_success = 88.0
        self.kpis["Rollback Success Rate"] = round(rollback_success, 1)

        # Guardrail Update Coverage: updates deployed relative to policy library size
        if updates is not None and not updates.empty and policies is not None and not policies.empty:
            update_cov = min(100.0, (updates["policy_id"].nunique() / policies["policy_id"].nunique()) * 100) if policies["policy_id"].nunique() > 0 else 77.0
        else:
            update_cov = 77.0
        self.kpis["Guardrail Update Coverage"] = round(update_cov, 1)

        # Effectiveness Improvement: avg effectiveness_delta from guardrail updates
        if updates is not None and not updates.empty:
            eff_improve = updates["effectiveness_delta"].mean()
        else:
            eff_improve = 12.4
        self.kpis["Effectiveness Improvement"] = round(eff_improve, 1)

        # Config Snapshot Coverage: % agents with a rollback-ready snapshot
        if snapshots is not None and not snapshots.empty:
            snap_cov = snapshots["rollback_available"].sum() / len(snapshots) * 100
        else:
            snap_cov = 90.0
        self.kpis["Config Snapshot Coverage"] = round(snap_cov, 1)

        # ── 6. Overall Scores ────────────────────────────────────────────────
        self.kpis["Identify Score"] = self.get_use_case_score("identify")
        self.kpis["Protect Score"] = self.get_use_case_score("protect")
        self.kpis["Detect Score"] = self.get_use_case_score("detect")
        self.kpis["Respond Score"] = self.get_use_case_score("respond")
        self.kpis["Recover Score"] = self.get_use_case_score("recover")

        # AI Security Posture Index: Weighted average of the 5 phase scores
        self.kpis["AI Readiness Index"] = self.get_ai_readiness_index()

        return self.kpis

    def get_use_case_score(self, uc: str) -> float:
        """Compute individual phase index score out of 100."""
        if uc == "identify":
            shadow_rate = self.kpis.get("Shadow AI Discovery Rate", 18.5)
            high_risk = self.kpis.get("High-Risk Agent Rate", 22.0)
            lineage_cov = self.kpis.get("Lineage Coverage Rate", 68.0)
            score = (100 - shadow_rate) * 0.4 + (100 - high_risk) * 0.35 + lineage_cov * 0.25
        elif uc == "protect":
            block_rate = self.kpis.get("Guardrail Block Rate", 91.0)
            lp_compliance = self.kpis.get("Least-Privilege Compliance Rate", 76.0)
            secrets_iso = self.kpis.get("Secrets Isolation Rate", 82.0)
            score = (block_rate * 0.4) + (lp_compliance * 0.3) + (secrets_iso * 0.3)
        elif uc == "detect":
            jailbreak_rate = self.kpis.get("Jailbreak Detection Rate", 82.0)
            attack_success = self.kpis.get("Red-Team Attack Success Rate", 22.0)
            anomaly_cov = self.kpis.get("Anomaly Detection Coverage", 88.0)
            score = (jailbreak_rate * 0.35) + ((100 - attack_success) * 0.35) + (anomaly_cov * 0.3)
        elif uc == "respond":
            auto_rate = self.kpis.get("Automated Containment Rate", 70.0)
            playbook_success = self.kpis.get("Playbook Success Rate", 93.0)
            hitl_rate = self.kpis.get("HITL Approval Rate", 89.0)
            score = (auto_rate * 0.4) + (playbook_success * 0.35) + (hitl_rate * 0.25)
        elif uc == "recover":
            rollback_success = self.kpis.get("Rollback Success Rate", 88.0)
            update_cov = self.kpis.get("Guardrail Update Coverage", 77.0)
            snap_cov = self.kpis.get("Config Snapshot Coverage", 90.0)
            score = (rollback_success * 0.45) + (update_cov * 0.30) + (snap_cov * 0.25)
        else:
            score = 75.0
        return round(min(100.0, max(0.0, score)), 1)

    def get_kpi(self, name: str) -> float:
        """Retrieve computed KPI value."""
        return self.kpis.get(name, 0.0)

    def get_ai_readiness_index(self) -> float:
        """Compute the AI Security Posture Index — average of the 5 NIST CSF phase scores."""
        scores = [
            self.get_use_case_score("identify"),
            self.get_use_case_score("protect"),
            self.get_use_case_score("detect"),
            self.get_use_case_score("respond"),
            self.get_use_case_score("recover"),
        ]
        return round(sum(scores) / 5.0, 1)
