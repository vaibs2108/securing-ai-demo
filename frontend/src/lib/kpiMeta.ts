export interface KpiMeta {
  name: string;
  unit: string;
  lowerIsBetter?: boolean;
  goodMax?: number; // for non-percentage metrics like MTTD/MTTC (hours)
}

export const PHASE_KPI_GROUPS: Record<string, KpiMeta[]> = {
  identify: [
    { name: "Shadow AI Discovery Rate", unit: "%", lowerIsBetter: true },
    { name: "High-Risk Agent Rate", unit: "%", lowerIsBetter: true },
    { name: "Lineage Coverage Rate", unit: "%" },
    { name: "Avg Agent Risk Score", unit: "", lowerIsBetter: true, goodMax: 100 },
  ],
  protect: [
    { name: "Guardrail Block Rate", unit: "%" },
    { name: "Least-Privilege Compliance Rate", unit: "%" },
    { name: "Secrets Isolation Rate", unit: "%" },
    { name: "PII Redaction Rate", unit: "%" },
  ],
  detect: [
    { name: "Jailbreak Detection Rate", unit: "%" },
    { name: "Red-Team Attack Success Rate", unit: "%", lowerIsBetter: true },
    { name: "MTTD", unit: "h", lowerIsBetter: true, goodMax: 4 },
    { name: "Anomaly Detection Coverage", unit: "%" },
  ],
  respond: [
    { name: "Automated Containment Rate", unit: "%" },
    { name: "MTTC", unit: "h", lowerIsBetter: true, goodMax: 4 },
    { name: "Playbook Success Rate", unit: "%" },
    { name: "HITL Approval Rate", unit: "%" },
  ],
  recover: [
    { name: "Rollback Success Rate", unit: "%" },
    { name: "Guardrail Update Coverage", unit: "%" },
    { name: "Effectiveness Improvement", unit: "pts" },
    { name: "Config Snapshot Coverage", unit: "%" },
  ],
  govern: [
    { name: "Policy Compliance Rate", unit: "%" },
    { name: "Critical Policy Violations", unit: "", lowerIsBetter: true },
    { name: "Governance Rule Coverage", unit: "%" },
    { name: "Framework Traceability Count", unit: "" },
  ],
};

export function kpiStatus(meta: KpiMeta, value: number): { label: string; colour: string } {
  if (meta.goodMax !== undefined && meta.unit === "h") {
    if (value <= meta.goodMax / 2) return { label: "OPTIMAL", colour: "var(--accent-green)" };
    if (value <= meta.goodMax) return { label: "STABLE", colour: "var(--accent-amber)" };
    return { label: "WARNING", colour: "var(--accent-red)" };
  }
  if (meta.unit === "pts") {
    if (value >= 12) return { label: "OPTIMAL", colour: "var(--accent-green)" };
    if (value >= 5) return { label: "STABLE", colour: "var(--accent-amber)" };
    return { label: "WARNING", colour: "var(--accent-red)" };
  }
  const effective = meta.lowerIsBetter ? 100 - value : value;
  if (effective >= 80) return { label: "OPTIMAL", colour: "var(--accent-green)" };
  if (effective >= 60) return { label: "STABLE", colour: "var(--accent-amber)" };
  if (effective >= 40) return { label: "WARNING", colour: "var(--accent-orange)" };
  return { label: "CRITICAL", colour: "var(--accent-red)" };
}
