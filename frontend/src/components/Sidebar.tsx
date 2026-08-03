import { Gauge, LayoutDashboard, MessagesSquare, Search, Sparkles, Target } from "lucide-react";
import type { ReactNode } from "react";

export type PageKey = "dashboard" | "recommendations" | "conversation" | "insights" | "research";

const NAV: { key: PageKey; label: string; icon: ReactNode }[] = [
  { key: "dashboard", label: "Daily dashboard", icon: <LayoutDashboard size={16} /> },
  { key: "recommendations", label: "Recommendations", icon: <Target size={16} /> },
  { key: "conversation", label: "Conversation panel", icon: <MessagesSquare size={16} /> },
  { key: "insights", label: "AI insights panel", icon: <Sparkles size={16} /> },
  { key: "research", label: "Research tab", icon: <Search size={16} /> },
];

export function Sidebar({ page, onNavigate }: { page: PageKey; onNavigate: (p: PageKey) => void }) {
  return (
    <aside
      className="flex w-56 shrink-0 flex-col border-r px-3 py-4"
      style={{ borderColor: "var(--line)", background: "var(--canvas-raised)" }}
    >
      <div className="mb-6 flex items-center gap-2 px-2">
        <div
          className="flex h-7 w-7 items-center justify-center rounded-md text-xs font-black"
          style={{ background: "var(--signal)", color: "var(--signal-ink)" }}
        >
          <Gauge size={15} />
        </div>
        <div>
          <p className="text-[13px] font-bold leading-tight">Opika Signal</p>
          <p className="text-[10px] leading-tight" style={{ color: "var(--ink-faint)" }}>
            CRM Sync — Phase 9
          </p>
        </div>
      </div>

      <nav className="grid gap-0.5">
        {NAV.map((item) => {
          const active = page === item.key;
          return (
            <button
              key={item.key}
              onClick={() => onNavigate(item.key)}
              className="flex items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-[13px] font-medium transition-colors"
              style={{
                background: active ? "var(--signal-ink)" : "transparent",
                color: active ? "var(--signal)" : "var(--ink-dim)",
              }}
            >
              {item.icon}
              {item.label}
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
