import { useEffect, useRef, useState } from "react";

/** Checkbox dropdown for picking multiple regions/countries at once - lets a
 * broad group (e.g. "GCC") and a specific country (e.g. "Qatar") be selected
 * together, instead of forcing one broad pill choice. */
export default function LocationMultiSelect({
  regions, countries, selected, onChange, disabled,
}: {
  regions: string[];
  countries: string[];
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

  function toggle(opt: string) {
    onChange(selected.includes(opt) ? selected.filter((x) => x !== opt) : [...selected, opt]);
  }

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        type="button"
        className="btn-secondary"
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        style={{ width: "100%", textAlign: "left", display: "flex", justifyContent: "space-between", alignItems: "center" }}
      >
        <span>{selected.length ? `${selected.length} selected` : "Select region(s) / country(ies)..."}</span>
        <span>{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div
          className="card"
          style={{ position: "absolute", zIndex: 20, top: "calc(100% + 4px)", left: 0, right: 0, maxHeight: 320, overflowY: "auto", padding: 12 }}
        >
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--dark-200)", marginBottom: 6, textTransform: "uppercase" }}>
            Regions
          </div>
          {regions.map((opt) => (
            <label key={opt} style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 0", fontSize: 13, cursor: "pointer" }}>
              <input type="checkbox" checked={selected.includes(opt)} onChange={() => toggle(opt)} style={{ width: "auto" }} />
              {opt}
            </label>
          ))}

          {countries.length > 0 && (
            <>
              <div style={{ fontSize: 11, fontWeight: 700, color: "var(--dark-200)", margin: "12px 0 6px", textTransform: "uppercase" }}>
                Countries
              </div>
              {countries.map((opt) => (
                <label key={opt} style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 0", fontSize: 13, cursor: "pointer" }}>
                  <input type="checkbox" checked={selected.includes(opt)} onChange={() => toggle(opt)} style={{ width: "auto" }} />
                  {opt}
                </label>
              ))}
            </>
          )}
        </div>
      )}

      {selected.length > 0 && (
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
          {selected.map((s) => (
            <span key={s} className="pill active" style={{ fontSize: 12, cursor: "pointer" }} onClick={() => toggle(s)}>
              {s} ✕
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
