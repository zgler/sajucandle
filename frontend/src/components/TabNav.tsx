"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/feed", label: "오늘", icon: "🔥" },
  { href: "/profile", label: "내 사주", icon: "🕯️" },
  { href: "/report", label: "감정서", icon: "📜" },
];

export default function TabNav() {
  const pathname = usePathname();

  return (
    <nav className="sticky top-0 z-50 bg-zinc-950/80 backdrop-blur-sm border-b border-zinc-800 print-hidden">
      <div className="flex">
        {TABS.map(({ href, label, icon }) => {
          const active = pathname === href || pathname.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              className={`flex-1 flex items-center justify-center gap-1.5 py-3.5 text-sm font-medium transition-colors ${
                active
                  ? "text-amber-400 border-b-2 border-amber-400"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              <span>{icon}</span>
              <span>{label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
