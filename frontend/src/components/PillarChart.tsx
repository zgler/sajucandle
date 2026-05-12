import type { SajuPillars } from "@/lib/types";
import { STEM_ELEMENT, ELEMENT_BG_COLORS } from "@/lib/constants";

interface Props {
  pillars: SajuPillars;
  showLabels?: boolean;
}

const PILLAR_NAMES = ["시주", "일주", "월주", "년주"] as const;

function getElementBg(char: string | null): string {
  if (!char) return "bg-zinc-700";
  const element = STEM_ELEMENT[char];
  if (!element) return "bg-zinc-700";
  return ELEMENT_BG_COLORS[element] ?? "bg-zinc-700";
}

export default function PillarChart({ pillars, showLabels = true }: Props) {
  const columns = [
    {
      label: "시주",
      stem: pillars.hour_stem,
      branch: pillars.hour_branch,
      empty: !pillars.hour_stem,
    },
    {
      label: "일주",
      stem: pillars.day_stem,
      branch: pillars.day_branch,
      empty: false,
    },
    {
      label: "월주",
      stem: pillars.month_stem,
      branch: pillars.month_branch,
      empty: false,
    },
    {
      label: "년주",
      stem: pillars.year_stem,
      branch: pillars.year_branch,
      empty: false,
    },
  ];

  return (
    <div className="flex gap-2 justify-center">
      {columns.map(({ label, stem, branch, empty }) => (
        <div key={label} className="flex flex-col items-center gap-1">
          {showLabels && (
            <span className="text-xs text-zinc-500 mb-1">{label}</span>
          )}

          {/* Stem (천간) */}
          <div
            className={`w-12 h-12 rounded-lg flex items-center justify-center text-xl font-bold text-zinc-950 ${
              empty ? "bg-zinc-700 text-zinc-500" : getElementBg(stem)
            }`}
          >
            {empty ? "?" : (stem ?? "?")}
          </div>

          {/* Branch (지지) */}
          <div
            className={`w-12 h-12 rounded-lg flex items-center justify-center text-xl font-bold text-zinc-950 ${
              empty ? "bg-zinc-800 text-zinc-600" : "bg-zinc-700 text-zinc-100"
            }`}
          >
            {empty ? "?" : (branch ?? "?")}
          </div>
        </div>
      ))}
    </div>
  );
}
