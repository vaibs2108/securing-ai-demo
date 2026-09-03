import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { PhaseKey } from "../lib/types";

export function SlackApprovalCard({
  uc,
  stageKey,
  summary,
  actionType = "suspend_target_agent",
  actionLabel = "Suspend the target agent",
}: {
  uc: PhaseKey;
  stageKey: string;
  summary: string;
  actionType?: "suspend_target_agent" | "restore_target_agent";
  actionLabel?: string;
}) {
  const requestMut = useMutation({
    mutationFn: () => api.requestApproval(uc, stageKey, actionType, summary),
  });

  const actionId = requestMut.data?.action_id;
  // Polls the real Slack decision — a human clicking Approve/Reject in
  // Slack doesn't push anything back to this tab, so this is how the card
  // finds out. Stops polling once resolved. refetchIntervalInBackground is
  // required here: the whole point is watching for a decision made while
  // the presenter has tabbed away to Slack itself — React Query's default
  // pause-when-unfocused behavior would otherwise leave the card stuck on
  // "waiting" until they click back into this tab.
  const statusQ = useQuery({
    queryKey: ["approval-status", actionId],
    queryFn: () => api.approvalStatus(actionId as string),
    enabled: !!actionId,
    refetchInterval: (query) => (query.state.data?.resolved ? false : 3000),
    refetchIntervalInBackground: true,
  });

  return (
    <div style={{ background: "#1a1d29", border: "1px solid #3a3d4d", borderRadius: 8, padding: "12px 14px", marginBottom: 16, maxWidth: 480 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
        <span style={{ fontSize: "1rem" }}>💬</span>
        <span style={{ fontSize: "0.78rem", fontWeight: 700, color: "#e8e8e8" }}>#securing-ai-alerts</span>
      </div>
      <div style={{ fontSize: "0.82rem", color: "#d8d8d8", lineHeight: 1.5, marginBottom: 10 }}>
        🚨 <strong>Securing AI — approval required</strong>
        <br />
        <span style={{ color: "#9fa4b8" }}>Action: {actionLabel}</span>
        <br />
        {summary.length > 240 ? summary.slice(0, 240) + "…" : summary}
      </div>

      {!requestMut.data && (
        <div style={{ display: "flex", gap: 8 }}>
          <button
            className="btn btn-small"
            style={{ background: "#2eb67d", borderColor: "#2eb67d", color: "#08111c" }}
            disabled={requestMut.isPending}
            onClick={() => requestMut.mutate()}
          >
            {requestMut.isPending ? "Posting to Slack…" : "Approve"}
          </button>
          <button className="btn btn-small" style={{ background: "#e01e5a", borderColor: "#e01e5a", color: "#fff" }} disabled>Reject</button>
        </div>
      )}
      {requestMut.data && !statusQ.data?.resolved && (
        <div style={{ fontSize: "0.78rem", color: "#9fe1cb" }}>
          ✅ Real Slack message posted to {requestMut.data.slack.channel ?? "the channel"}. Waiting for a real human
          to click Approve or Reject in Slack — this card can't fake that part for you.
          {requestMut.data.slack.permalink && (
            <div style={{ marginTop: 8 }}>
              <a
                href={requestMut.data.slack.permalink}
                target="_blank"
                rel="noreferrer"
                style={{ color: "#4a90e2", fontWeight: 700, textDecoration: "none" }}
              >
                🔗 Open this message in Slack →
              </a>
              <div style={{ color: "#8a8d9d", marginTop: 2 }}>Opens the real message — you'll need to already be signed into this Slack workspace.</div>
            </div>
          )}
        </div>
      )}
      {statusQ.data?.resolved && (
        <div
          style={{
            fontSize: "0.8rem",
            fontWeight: 700,
            color: statusQ.data.decision === "approve" ? "#9fe1cb" : "#f7c1c1",
          }}
        >
          {statusQ.data.decision === "approve" ? "✅ Approved" : "❌ Rejected"} in Slack by @{statusQ.data.approver}
          <div style={{ fontWeight: 400, fontSize: "0.76rem", color: "#c4c6d4", marginTop: 4 }}>{statusQ.data.status_note}</div>
        </div>
      )}
      {requestMut.isError && <div style={{ fontSize: "0.78rem", color: "#f7c1c1" }}>Couldn't reach Slack. Check the real bot token.</div>}
    </div>
  );
}
