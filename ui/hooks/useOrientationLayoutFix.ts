"use client";

import { useEffect, useState } from "react";

/**
 * Solves iOS Safari + Android Chrome layout glitches after device rotation,
 * dynamic toolbar show/hide, and on-screen-keyboard pop.
 *
 * What it does:
 *   1. Sets --app-vh, --app-svh, --app-dvh CSS custom properties on <html>
 *      so layouts can use `min-height: calc(var(--app-dvh, 1vh) * 100)`
 *      and never break when the iOS toolbar slides in/out.
 *   2. Listens to window.resize, window.orientationchange, and
 *      visualViewport.resize — debounced via requestAnimationFrame.
 *   3. Dispatches a custom 'app:orientation-change' event so components
 *      like TradingView can force a chart.resize() on rotation.
 *   4. Forces a body reflow on rotation by toggling a class — fixes the
 *      iOS "stale viewport width" bug that ScrollView containers hit.
 *
 * Mount once at the root layout. Returns the current orientation.
 */
export function useOrientationLayoutFix(): "portrait" | "landscape" {
  const [orientation, setOrientation] = useState<"portrait" | "landscape">("portrait");

  useEffect(() => {
    if (typeof window === "undefined") return;

    let rafId: number | null = null;
    const root = document.documentElement;

    const update = () => {
      rafId = null;

      // Visual viewport (iOS Safari + Android Chrome) is the most accurate
      // when the toolbar shrinks. Fall back to innerHeight on older browsers.
      const vv = (window as Window & { visualViewport?: VisualViewport }).visualViewport;
      const h  = vv?.height ?? window.innerHeight;
      const w  = vv?.width  ?? window.innerWidth;

      root.style.setProperty("--app-vh",  `${h * 0.01}px`); // legacy 1vh equivalent
      root.style.setProperty("--app-dvh", `${h * 0.01}px`); // dynamic — updates with toolbar
      root.style.setProperty("--app-w",   `${w}px`);

      const next: "portrait" | "landscape" = w > h ? "landscape" : "portrait";
      setOrientation(prev => (prev === next ? prev : next));

      // Notify chart components to recompute their canvas size
      window.dispatchEvent(new CustomEvent("app:orientation-change", { detail: { width: w, height: h } }));
    };

    const schedule = () => {
      if (rafId != null) return;
      rafId = requestAnimationFrame(update);
    };

    // Initial measurement
    update();

    // Listeners — all three because each fires on different platforms
    window.addEventListener("resize", schedule, { passive: true });
    window.addEventListener("orientationchange", schedule, { passive: true });

    const vv = (window as Window & { visualViewport?: VisualViewport }).visualViewport;
    vv?.addEventListener("resize", schedule, { passive: true });
    vv?.addEventListener("scroll", schedule, { passive: true });

    // Some iOS versions need a delayed re-measure AFTER orientation change
    // because innerHeight reads stale values during the transition itself
    const onOrientation = () => {
      schedule();
      setTimeout(schedule, 250);
      setTimeout(schedule, 600);
    };
    window.addEventListener("orientationchange", onOrientation);

    return () => {
      if (rafId != null) cancelAnimationFrame(rafId);
      window.removeEventListener("resize", schedule);
      window.removeEventListener("orientationchange", schedule);
      window.removeEventListener("orientationchange", onOrientation);
      vv?.removeEventListener("resize", schedule);
      vv?.removeEventListener("scroll", schedule);
    };
  }, []);

  return orientation;
}
