import { useEffect, useRef, useState } from "react";

type ClusterOption = { key: string; label: string; products: string[]; role: string };

/** Checkbox dropdown for picking ICP title clusters, grouped by product -
 * same collapsed/expand pattern as LocationMultiSelect, since the full list
 * (scripts/icp_titles.py's ~50 canonical families) is too long to show
 * inline without a summary. */
export default function ClusterMultiSelect({
  options, selected, onChange, disabled,
}: {
  options: ClusterOption[];
  selected: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  function toggle(key: string) {
    onChange(selected.includes(key) ? selected.filter((x) => x !== key) : [...selected, key]);
  }

  const byProduct: Record<string, ClusterOption[]> = {};
  for (const opt of options) {
    for (const p of opt.products) {
      (byProduct[p] ||= []).push(opt);
    }
  }
  const labelOf = (key: string) => options.find((o) => o.key === key)?.label ?? key;

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        type="button"
        className="btn-secondary"
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        style={{ width: "100%", textAlign: "left", display: "flex", justifyContent: "space-between", alignItems: "center" }}
      >
        <span>{selected.length ? `${selected.length} cluster(s) selected` : "Select ICP cluster(s)..."}</span>
        <span>{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div
          className="card"
          style={{ position: "absolute", zIndex: 20, top: "calc(100% + 4px)", left: 0, right: 0, maxHeight: 360, overflowY: "auto", padding: 12 }}
        >
          {Object.entries(byProduct).map(([product, opts]) => (
            <div key={product} style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: "var(--dark-200)", marginBottom: 6, textTransform: "uppercase" }}>
                {product}
              </div>
              {opts.map((opt) => (
                <label key={opt.key} style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 0", fontSize: 13, cursor: "pointer" }}>
                  <input type="checkbox" checked={selected.includes(opt.key)} onChange={() => toggle(opt.key)} style={{ width: "auto" }} />
                  {opt.label}
                  <span style={{ fontSize: 11, color: "var(--dark-200)" }}>({opt.role})</span>
                </label>
              ))}
            </div>
          ))}
        </div>
      )}

      {selected.length > 0 && (
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
          {selected.map((s) => (
            <span key={s} className="pill active" style={{ fontSize: 12, cursor: "pointer" }} onClick={() => toggle(s)}>
              {labelOf(s)} ✕
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
