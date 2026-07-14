import type { HealthStatus } from "../lib/types";

const LABEL: Record<HealthStatus, string> = {
  healthy: "Backend connected",
  unhealthy: "Backend unreachable",
  connecting: "Connecting…",
};

const DOT: Record<HealthStatus, string> = {
  healthy: "bg-green-w",
  unhealthy: "bg-rose",
  connecting: "bg-amber-d",
};

interface Props {
  status: HealthStatus;
}

export function HealthPill({ status }: Props) {
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-[11px] text-fg-dim">
      <span
        className={`inline-block h-2 w-2 rounded-full ${DOT[status]} shadow-[0_0_6px_currentColor]`}
        aria-hidden="true"
      />
      {LABEL[status]}
    </span>
  );
}
