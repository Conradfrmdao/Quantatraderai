"use client";
import { SignUp } from "@clerk/nextjs";
import { Suspense } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import dynamic from "next/dynamic";
import { Logo, LogoWordmark } from "@/components/Logo";
import { useIsMobile } from "@/hooks/useIsMobile";

const CanvasRevealEffect = dynamic(
  () => import("@/components/ui/canvas-reveal-effect").then((m) => m.CanvasRevealEffect),
  { ssr: false }
);

const clerkAppearance = {
  variables: {
    colorBackground: "rgba(10,10,10,0.85)",
    colorInputBackground: "rgba(255,255,255,0.05)",
    colorInputText: "#ffffff",
    colorText: "#ffffff",
    colorTextSecondary: "rgba(255,255,255,0.5)",
    colorPrimary: "#ffffff",
    colorNeutral: "#ffffff",
    colorDanger: "#f87171",
    borderRadius: "12px",
    fontFamily: "inherit",
  },
  elements: {
    card: {
      background: "rgba(255,255,255,0.03)",
      backdropFilter: "blur(28px)",
      border: "1px solid rgba(255,255,255,0.08)",
      boxShadow: "none",
    },
    headerTitle: { color: "#ffffff" },
    headerSubtitle: { color: "rgba(255,255,255,0.45)" },
    formButtonPrimary: {
      background: "#ffffff",
      color: "#000000",
      fontWeight: "600",
    },
    formFieldInput: {
      background: "rgba(255,255,255,0.04)",
      borderColor: "rgba(255,255,255,0.1)",
      color: "#ffffff",
    },
    formFieldLabel: { color: "rgba(255,255,255,0.55)" },
    footerActionLink: { color: "#ffffff", fontWeight: "600" },
    footerActionText: { color: "rgba(255,255,255,0.6)" },
    footer: { color: "rgba(255,255,255,0.5)" },
    footerPages: { color: "rgba(255,255,255,0.4)" },
    footerPagesLink: { color: "rgba(255,255,255,0.55)" },
    dividerLine: { background: "rgba(255,255,255,0.08)" },
    dividerText: { color: "rgba(255,255,255,0.35)" },
    socialButtonsBlockButton: {
      background: "rgba(255,255,255,0.04)",
      borderColor: "rgba(255,255,255,0.1)",
      color: "#ffffff",
    },
    badge: { color: "rgba(255,255,255,0.35)", background: "transparent", border: "none" },
  },
};

export default function SignUpPage() {
  const isMobile = useIsMobile();
  return (
    <div style={{
      position: "relative", minHeight: "100vh", background: "#000",
      color: "#fff", display: "flex", flexDirection: "column", overflow: "hidden",
    }}>
      {/* WebGL background */}
      <div style={{ position: "absolute", inset: 0, zIndex: 0 }}>
        <CanvasRevealEffect className="w-full h-full" revealDuration={3} />
      </div>
      {/* Vignette */}
      <div style={{
        position: "absolute", inset: 0, zIndex: 0, pointerEvents: "none",
        background: "radial-gradient(ellipse 90% 90% at 50% 50%, rgba(0,0,0,0.3) 0%, rgba(0,0,0,0.72) 65%, rgba(0,0,0,0.95) 100%)",
      }} />

      {/* Navbar */}
      <nav style={{
        position: "relative", zIndex: 10,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: isMobile ? "0 16px" : "0 28px", height: 60,
        borderBottom: "1px solid rgba(255,255,255,0.06)",
      }}>
        <LogoWordmark size={28} />
        <Link href="/" style={{
          display: "inline-flex", alignItems: "center", gap: 6,
          padding: "8px 14px", color: "rgba(255,255,255,0.4)",
          fontSize: 14, textDecoration: "none",
        }}>
          <ArrowLeft size={14} /> Back
        </Link>
      </nav>

      {/* Centered card */}
      <div style={{
        flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
        padding: "32px 20px", position: "relative", zIndex: 10,
      }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 24, width: "100%", maxWidth: 440 }}>
          <Logo size={48} />
          <Suspense fallback={
            <div style={{
              height: 380, width: "100%", borderRadius: 24,
              background: "rgba(255,255,255,0.03)",
              border: "1px solid rgba(255,255,255,0.08)",
            }} />
          }>
            <SignUp appearance={clerkAppearance} />
          </Suspense>
        </div>
      </div>
    </div>
  );
}
