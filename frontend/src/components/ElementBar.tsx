interface Props {
  distribution: Record<string, number>;
}

const ELEMENTS = [
  { key: "Wood", label: "木", color: "bg-wood" },
  { key: "Fire", label: "火", color: "bg-fire" },
  { key: "Earth", label: "土", color: "bg-earth" },
  { key: "Metal", label: "金", color: "bg-metal" },
  { key: "Water", label: "水", color: "bg-water" },
];

export default function ElementBar({ distribution }: Props) {
  const total = Object.values(distribution).reduce((a, b) => a + b, 0) || 1;

  return (
    <div className="space-y-2">
      <p className="text-xs text-zinc-500 uppercase tracking-wide">오행 분포</p>
      {ELEMENTS.map(({ key, label, color }) => {
        // Try both English and Korean keys
        const value =
          distribution[key] ??
          distribution[key.toLowerCase()] ??
          distribution[label] ??
          0;
        const pct = Math.round((value / total) * 100);

        return (
          <div key={key} className="flex items-center gap-2">
            <span className="text-sm font-bold text-zinc-300 w-5 text-center">
              {label}
            </span>
            <div className="flex-1 bg-zinc-800 rounded-full h-2">
              <div
                className={`${color} h-2 rounded-full transition-all duration-700`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="text-xs text-zinc-500 w-8 text-right">{pct}%</span>
          </div>
        );
      })}
    </div>
  );
}
