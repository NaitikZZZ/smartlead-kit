import { useState } from "react";

/** A small "type your own" affordance for any list/checkbox picker - so the
 * user is never locked into whatever options were pre-populated. Enter (or
 * the Add button) appends the typed text as just another selected item. */
export default function AddCustomChip({
  onAdd, placeholder = "Type your own and press Enter...", disabled,
}: { onAdd: (value: string) => void; placeholder?: string; disabled?: boolean }) {
  const [value, setValue] = useState("");

  function commit() {
    const v = value.trim();
    if (!v) return;
    onAdd(v);
    setValue("");
  }

  return (
    <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
      <input
        type="text"
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); commit(); } }}
        style={{ flex: 1 }}
      />
      <button type="button" className="btn-secondary" disabled={disabled || !value.trim()} onClick={commit}>
        Add
      </button>
    </div>
  );
}
