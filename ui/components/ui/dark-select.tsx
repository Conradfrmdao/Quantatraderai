"use client";
/**
 * DarkSelect — a fully-styled custom dropdown that looks correct in every browser.
 * Native <select> can't be reliably styled in all OS/browser combos.
 * Use this anywhere you need a dropdown in the dark UI.
 */
import { useState, useRef, useEffect } from "react";
import { ChevronDown } from "lucide-react";

export interface SelectOption {
  value: string;
  label: string;
  sub?:  string;  // optional small line below label
}

interface Props {
  options:   SelectOption[];
  value:     string;
  onChange:  (value: string) => void;
  placeholder?: string;
  style?:    React.CSSProperties;
  disabled?: boolean;
}

export function DarkSelect({ options, value, onChange, placeholder = "Select…", style, disabled }: Props) {
  const [open, setOpen]       = useState(false);
  const containerRef          = useRef<HTMLDivElement>(null);

  const selected = options.find(o => o.value === value);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div ref={containerRef} style={{ position: "relative", ...style }}>
      {/* Trigger button */}
      <button
        type="button"
        disabled={disabled}
        onClick={() => !disabled && setOpen(o => !o)}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          padding: "10px 14px",
          borderRadius: 10,
          background: open ? "rgba(255,255,255,0.08)" : "rgba(255,255,255,0.04)",
          border: `1px solid ${open ? "rgba(255,255,255,0.2)" : "rgba(255,255,255,0.1)"}`,
          color: selected ? "#fff" : "rgba(255,255,255,0.35)",
          fontSize: 13,
          fontWeight: selected ? 500 : 400,
          cursor: disabled ? "default" : "pointer",
          textAlign: "left",
          transition: "all 0.15s",
          outline: "none",
          opacity: disabled ? 0.5 : 1,
        }}
      >
        <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {selected ? selected.label : placeholder}
        </span>
        <ChevronDown
          size={14}
          style={{
            color: "rgba(255,255,255,0.4)",
            flexShrink: 0,
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform 0.2s",
          }}
        />
      </button>

      {/* Dropdown list */}
      {open && (
        <div style={{
          position: "absolute",
          top: "calc(100% + 6px)",
          left: 0,
          right: 0,
          zIndex: 1000,
          background: "#111",
          border: "1px solid rgba(255,255,255,0.12)",
          borderRadius: 12,
          overflow: "hidden",
          boxShadow: "0 16px 40px rgba(0,0,0,0.6)",
          maxHeight: 280,
          overflowY: "auto",
        }}>
          {options.map(opt => {
            const isSelected = opt.value === value;
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => { onChange(opt.value); setOpen(false); }}
                style={{
                  width: "100%",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "flex-start",
                  gap: 2,
                  padding: "10px 14px",
                  background: isSelected ? "rgba(255,255,255,0.08)" : "transparent",
                  border: "none",
                  borderBottom: "1px solid rgba(255,255,255,0.04)",
                  color: isSelected ? "#fff" : "rgba(255,255,255,0.75)",
                  fontSize: 13,
                  fontWeight: isSelected ? 600 : 400,
                  cursor: "pointer",
                  textAlign: "left",
                  transition: "background 0.1s",
                }}
                onMouseEnter={e => { if (!isSelected) (e.target as HTMLElement).style.background = "rgba(255,255,255,0.04)"; }}
                onMouseLeave={e => { if (!isSelected) (e.target as HTMLElement).style.background = "transparent"; }}
              >
                <span>{opt.label}</span>
                {opt.sub && (
                  <span style={{ fontSize: 11, color: "rgba(255,255,255,0.35)", fontWeight: 400 }}>{opt.sub}</span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
