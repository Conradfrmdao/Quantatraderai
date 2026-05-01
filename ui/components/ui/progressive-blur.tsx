'use client';

import React from "react";
import { cn } from "@/lib/utils";

interface ProgressiveBlurProps {
  className?: string;
  direction?: "top" | "bottom" | "left" | "right";
  blurLevels?: number;
  blurIntensity?: number;
}

export function ProgressiveBlur({
  className,
  direction = "bottom",
  blurLevels = 8,
  blurIntensity = 4,
}: ProgressiveBlurProps) {
  const layers = Array.from({ length: blurLevels }, (_, i) => i);

  const getGradientStyle = (index: number): React.CSSProperties => {
    const step = 1 / blurLevels;
    const start = index * step;
    const end = (index + 1) * step;

    const transparent = "rgba(0,0,0,0)";
    const opaque = "rgba(0,0,0,1)";

    let maskImage: string;
    switch (direction) {
      case "top":
        maskImage = `linear-gradient(to bottom, ${opaque} ${start * 100}%, ${transparent} ${end * 100}%)`;
        break;
      case "left":
        maskImage = `linear-gradient(to right, ${opaque} ${start * 100}%, ${transparent} ${end * 100}%)`;
        break;
      case "right":
        maskImage = `linear-gradient(to left, ${opaque} ${start * 100}%, ${transparent} ${end * 100}%)`;
        break;
      case "bottom":
      default:
        maskImage = `linear-gradient(to top, ${opaque} ${start * 100}%, ${transparent} ${end * 100}%)`;
        break;
    }

    return {
      backdropFilter: `blur(${((index + 1) / blurLevels) * blurIntensity}px)`,
      WebkitBackdropFilter: `blur(${((index + 1) / blurLevels) * blurIntensity}px)`,
      maskImage,
      WebkitMaskImage: maskImage,
    };
  };

  return (
    <div
      className={cn(
        "pointer-events-none absolute inset-0",
        className
      )}
    >
      {layers.map((i) => (
        <div key={i} className="absolute inset-0" style={getGradientStyle(i)} />
      ))}
    </div>
  );
}
