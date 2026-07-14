import { useState } from "react";

interface Props {
  data: unknown;
  label?: string;
}

export function RawJson({ data, label = "Raw JSON" }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <details
      className="mt-2 text-[11px] text-fg-faint"
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
    >
      <summary className="cursor-pointer font-mono uppercase tracking-wide hover:text-fg-dim">
        {label}
      </summary>
      <pre className="mt-1.5 max-h-48 overflow-auto rounded border border-line-soft bg-surface-2 p-2 font-mono text-[10.5px] whitespace-pre-wrap text-fg-dim">
        {JSON.stringify(data, null, 2)}
      </pre>
    </details>
  );
}
