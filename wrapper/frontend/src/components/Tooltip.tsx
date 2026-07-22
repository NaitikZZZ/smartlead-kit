import { useLayoutEffect, useRef, useState, type ReactNode } from "react";

/**
 * Hover/focus tooltip with edge-aware positioning: it flips above/below and
 * clamps horizontally so the bubble never clips off-screen. Wrap any element,
 * or render just the info dot (no children) next to a label.
 */
export default function Tooltip({ text, children }: { text: string; children?: ReactNode }) {
  const wrapRef = useRef<HTMLSpanElement>(null);
  const tipRef = useRef<HTMLSpanElement>(null);
  const [show, setShow] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number }>({ top: -9999, left: -9999 });

  useLayoutEffect(() => {
    if (!show || !wrapRef.current || !tipRef.current) return;
    const anchor = wrapRef.current.getBoundingClientRect();
    const tip = tipRef.current;
    const tw = tip.offsetWidth;
    const th = tip.offsetHeight;
    const gap = 8;
    // Prefer below; flip above only if there isn't room below.
    let top = anchor.bottom + gap;
    if (top + th > window.innerHeight - gap && anchor.top - th - gap > gap) {
      top = anchor.top - th - gap;
    }
    let left = anchor.left + anchor.width / 2 - tw / 2;
    left = Math.max(gap, Math.min(left, window.innerWidth - tw - gap));
    setPos({ top, left });
  }, [show]);

  return (
    <span
      ref={wrapRef}
      className="tooltip"
      tabIndex={0}
      aria-label={text}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onFocus={() => setShow(true)}
      onBlur={() => setShow(false)}
    >
      {children ?? <InfoDot />}
      <span
        ref={tipRef}
        className="tip-fixed"
        role="tooltip"
        style={{ top: pos.top, left: pos.left, opacity: show ? 1 : 0, visibility: show ? "visible" : "hidden" }}
      >
        {text}
      </span>
    </span>
  );
}

function InfoDot() {
  return (
    <svg className="info-dot" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <circle cx="10" cy="10" r="8" />
      <path d="M10 9v4.5" strokeLinecap="round" />
      <circle cx="10" cy="6.5" r="0.9" fill="currentColor" stroke="none" />
    </svg>
  );
}
