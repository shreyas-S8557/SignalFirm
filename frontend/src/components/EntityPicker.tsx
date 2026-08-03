import type { EntityRef } from "../lib/types";

export function EntityPicker({
  label,
  entities,
  selectedId,
  onSelect,
}: {
  label: string;
  entities: EntityRef[];
  selectedId?: string;
  onSelect: (id: string) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-xs font-semibold" style={{ color: "var(--ink-dim)" }}>
      {label}
      <select
        value={selectedId ?? ""}
        onChange={(e) => onSelect(e.target.value)}
        className="rounded-md border px-2 py-1.5 text-sm font-medium"
        style={{ borderColor: "var(--line-strong)", background: "var(--canvas-raised)", color: "var(--ink)" }}
      >
        {entities.map((e) => (
          <option key={e.id} value={e.id}>
            {e.name}
            {e.companyName ? ` — ${e.companyName}` : ""}
          </option>
        ))}
      </select>
    </label>
  );
}
