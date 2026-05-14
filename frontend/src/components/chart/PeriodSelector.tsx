"use client";

const PERIODS = [
  { label: "1M", months: 1 },
  { label: "3M", months: 3 },
  { label: "6M", months: 6 },
  { label: "1Y", months: 12 },
  { label: "ALL", months: 60 },
];

interface Props {
  selected: number;
  onSelect: (months: number) => void;
}

export default function PeriodSelector({ selected, onSelect }: Props) {
  return (
    <div className="flex gap-1 justify-center py-2 bg-zinc-950 border-b border-zinc-800">
      {PERIODS.map(({ label, months }) => (
        <button
          key={label}
          onClick={() => onSelect(months)}
          className={`text-xs px-3 py-1 rounded ${
            selected === months
              ? "text-amber-400 bg-amber-400/15 font-semibold"
              : "text-zinc-500 hover:text-zinc-300"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
