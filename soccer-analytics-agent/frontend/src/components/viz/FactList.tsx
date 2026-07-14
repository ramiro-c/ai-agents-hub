import { useState } from "react";
import type { RecallResult } from "../../lib/types";

interface Props {
  data: RecallResult;
}

export function FactList({ data }: Props) {
  const facts = data.facts ?? [];
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? facts : facts.slice(0, 10);

  if (facts.length === 0) {
    return <p className="text-[12px] text-fg-dim">No facts recalled.</p>;
  }

  return (
    <div>
      <ol className="list-inside list-decimal space-y-1.5">
        {shown.map((item) => (
          <li
            key={item.id}
            className="text-[12.5px] leading-snug text-fg-dim"
          >
            {item.content}
          </li>
        ))}
      </ol>
      {facts.length > 10 && !expanded && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="mt-2 font-mono text-[11px] text-accent hover:text-accent-dim"
        >
          Show all {facts.length} facts
        </button>
      )}
    </div>
  );
}
