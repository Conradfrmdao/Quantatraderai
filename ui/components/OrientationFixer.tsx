"use client";

import { useOrientationLayoutFix } from "@/hooks/useOrientationLayoutFix";

export function OrientationFixer() {
  useOrientationLayoutFix();
  return null;
}
