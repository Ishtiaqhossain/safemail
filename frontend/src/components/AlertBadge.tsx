import type { Severity } from "@/types";

const COLORS: Record<Severity, string> = {
  critical: "#dc2626",
  high: "#ea580c",
  medium: "#d97706",
  low: "#65a30d",
};

const LABELS: Record<Severity, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
};

interface Props {
  severity: Severity;
}

export function AlertBadge({ severity }: Props) {
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: 4,
        fontSize: 12,
        fontWeight: 600,
        color: "#fff",
        backgroundColor: COLORS[severity],
        textTransform: "uppercase",
      }}
    >
      {LABELS[severity]}
    </span>
  );
}
