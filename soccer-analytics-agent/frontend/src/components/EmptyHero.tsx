const CHIPS = [
  "¿Quién ganó el Mundial 2026?",
  "¿Cuál es el Elo de Argentina?",
  "Predice España vs Argentina",
  "Últimos 5 partidos de Argentina",
  "Historial Argentina vs España",
  "¿Quién salió tercero en 2026?",
];

interface Props {
  onPick: (query: string) => void;
}

export function EmptyHero({ onPick }: Props) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 px-4 py-12">
      <div className="text-center">
        <h2 className="text-xl font-semibold text-fg">
          Preguntame de fútbol internacional
        </h2>
        <p className="mt-2 text-[14px] text-fg-dim">
          Partidos, selecciones, Elo, predicciones e historiales
        </p>
      </div>

      <div className="flex max-w-xl flex-wrap justify-center gap-2">
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
