interface Props {
  status: string;
  message: string;
}

export function StatusBadge({ status, message }: Props) {
  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-green-w/40 bg-green-w/10 px-3 py-1">
      <span className="h-1.5 w-1.5 rounded-full bg-green-w" aria-hidden="true" />
      <span className="font-mono text-[12px] text-green-w">
        {status === "remembered" ? "Remembered" : message}
      </span>
    </div>
  );
}
