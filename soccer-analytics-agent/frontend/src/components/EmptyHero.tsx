const CHIPS = [
  "Who won the 2022 World Cup?",
  "What's Argentina's Elo rating?",
  "Predict Argentina vs France",
  "Show me Brazil's last 5 matches",
  "Head-to-head: Argentina vs Germany",
  "Compare Messi vs Ronaldo stats",
];

interface Props {
  onPick: (query: string) => void;
}

export function EmptyHero({ onPick }: Props) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 px-4 py-12">
      <div className="text-center">
        <h2 className="text-xl font-semibold text-fg">
          Ask me about international football
        </h2>
        <p className="mt-2 text-[14px] text-fg-dim">
          Ask about matches, teams, Elo ratings, predictions, and head-to-head
          records
        </p>
      </div>

      <div className="flex max-w-lg flex-wrap justify-center gap-2">
        {CHIPS.map((chip) => (
          <button
            key={chip}
            type="button"
            onClick={() => onPick(chip)}
            className="rounded-full border border-line-soft bg-surface px-3.5 py-1.5 text-[13px] text-fg-dim transition-colors hover:border-accent hover:text-fg"
          >
            {chip}
          </button>
        ))}
      </div>
    </div>
  );
}
