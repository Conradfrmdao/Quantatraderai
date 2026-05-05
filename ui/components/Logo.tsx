'use client';

import React from "react";
import { APP_NAME } from "@/lib/constants";

interface LogoProps {
  size?: number;
  className?: string;
}

export function Logo({ size = 36, className = "" }: LogoProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-label={APP_NAME}
    >
      <line x1="7"  y1="4"  x2="7"  y2="36" stroke="white" strokeWidth="1" strokeLinecap="round" opacity="0.3" />
      <line x1="16" y1="2"  x2="16" y2="38" stroke="white" strokeWidth="1" strokeLinecap="round" opacity="0.3" />
      <line x1="25" y1="6"  x2="25" y2="34" stroke="white" strokeWidth="1" strokeLinecap="round" opacity="0.3" />
      <line x1="34" y1="3"  x2="34" y2="37" stroke="white" strokeWidth="1" strokeLinecap="round" opacity="0.3" />

      <rect x="4"  y="12" width="6" height="18" rx="1" fill="white" />
      <rect x="13" y="8"  width="6" height="14" rx="1" fill="none" stroke="white" strokeWidth="1.5" />
      <rect x="22" y="16" width="6" height="10" rx="1" fill="white" />
      <rect x="31" y="10" width="6" height="20" rx="1" fill="none" stroke="white" strokeWidth="1.5" />

      <path
        d="M4 30 L13 20 L22 24 L37 12"
        stroke="white"
        strokeWidth="1"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeDasharray="2 2"
        opacity="0.5"
      />
    </svg>
  );
}

export function LogoWordmark({ size = 36 }: { size?: number }) {
  return (
    <div className="flex items-center gap-2.5">
      <Logo size={size} />
      <span
        style={{
          fontSize: size * 0.42,
          fontWeight: 700,
          color: "#fff",
          letterSpacing: "-0.03em",
          lineHeight: 1,
        }}
      >
        {APP_NAME.slice(0, -2)}<span style={{ opacity: 0.5 }}>{APP_NAME.slice(-2)}</span>
      </span>
    </div>
  );
}
