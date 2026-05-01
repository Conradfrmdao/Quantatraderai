'use client';

import React, { useRef, useEffect } from "react";
import { cn } from "@/lib/utils";

interface InfiniteSliderProps {
  children: React.ReactNode;
  duration?: number;
  durationOnHover?: number;
  direction?: "horizontal" | "vertical";
  reverse?: boolean;
  gap?: number;
  className?: string;
}

export function InfiniteSlider({
  children,
  duration = 30,
  durationOnHover,
  direction = "horizontal",
  reverse = false,
  gap = 32,
  className,
}: InfiniteSliderProps) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const wrapper = wrapperRef.current;
    if (!wrapper) return;

    const handleMouseEnter = () => {
      if (durationOnHover !== undefined) {
        wrapper.style.setProperty("--duration", `${durationOnHover}s`);
      }
    };
    const handleMouseLeave = () => {
      wrapper.style.setProperty("--duration", `${duration}s`);
    };

    wrapper.addEventListener("mouseenter", handleMouseEnter);
    wrapper.addEventListener("mouseleave", handleMouseLeave);
    return () => {
      wrapper.removeEventListener("mouseenter", handleMouseEnter);
      wrapper.removeEventListener("mouseleave", handleMouseLeave);
    };
  }, [duration, durationOnHover]);

  const isHorizontal = direction === "horizontal";
  const animationName = isHorizontal
    ? reverse
      ? "slider-reverse-x"
      : "slider-x"
    : reverse
    ? "slider-reverse-y"
    : "slider-y";

  return (
    <>
      <style>{`
        @keyframes slider-x {
          0%   { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        @keyframes slider-reverse-x {
          0%   { transform: translateX(-50%); }
          100% { transform: translateX(0); }
        }
        @keyframes slider-y {
          0%   { transform: translateY(0); }
          100% { transform: translateY(-50%); }
        }
        @keyframes slider-reverse-y {
          0%   { transform: translateY(-50%); }
          100% { transform: translateY(0); }
        }
        .infinite-slider-track {
          animation-name: var(--anim-name);
          animation-duration: var(--duration);
          animation-timing-function: linear;
          animation-iteration-count: infinite;
          will-change: transform;
        }
        .infinite-slider-track:hover {
          animation-play-state: paused;
        }
      `}</style>
      <div
        ref={wrapperRef}
        className={cn("overflow-hidden", className)}
        style={
          {
            "--duration": `${duration}s`,
            "--anim-name": animationName,
          } as React.CSSProperties
        }
      >
        <div
          ref={contentRef}
          className="infinite-slider-track flex w-max"
          style={{
            flexDirection: isHorizontal ? "row" : "column",
            gap,
          }}
        >
          {/* Render children twice for seamless loop */}
          {children}
          {children}
        </div>
      </div>
    </>
  );
}
