import { useState, type ReactNode } from "react";

/** Click-to-reveal wrapper — shows only `trigger` until clicked, then
 * reveals `children` below it. Used to keep dense stage pages scannable:
 * headline/badge visible, explanatory copy hidden until the user actually
 * wants it. */
export function Expandable({ trigger, children, defaultOpen = false }: { trigger: ReactNode; children: ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        style={{
          all: "unset",
          cursor: "pointer",
          display: "inline-flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        {trigger}
        <span style={{ fontSize: "0.62rem", color: "var(--text-muted)" }}>{open ? "▲" : "▼"}</span>
      </button>
      {open && <div style={{ marginTop: 4 }}>{children}</div>}
    </div>
  );
}
