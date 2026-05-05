import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import { ToastProvider } from "@/components/Toast";
import { SignOutGuard } from "@/components/SignOutGuard";
import { APP_NAME, APP_TAGLINE } from "@/lib/constants";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: `${APP_NAME} — ${APP_TAGLINE}`,
  description: "Multi-venue AI trading agent. Connects to Hyperliquid, Binance, OANDA, MetaTrader, Alpaca, IBKR and 100+ exchanges. 24/7 autonomous trading with collective AI council decision-making.",
  icons: {
    icon: [
      { url: "/icon.svg?v=2",          type: "image/svg+xml" },
      { url: "/favicon-32x32.png?v=2", sizes: "32x32",  type: "image/png" },
      { url: "/favicon-16x16.png?v=2", sizes: "16x16",  type: "image/png" },
      { url: "/favicon.ico",           sizes: "any" },
    ],
    apple: [
      { url: "/apple-touch-icon.png?v=2", sizes: "180x180", type: "image/png" },
    ],
    other: [
      { rel: "mask-icon", url: "/safari-pinned-tab.svg?v=2", color: "#4ade80" },
    ],
  },
  manifest: "/site.webmanifest",
  themeColor: "#000000",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider afterSignOutUrl="/">
      <html lang="en" className="h-full">
        <body className={`${inter.className} min-h-full`}>
          <ToastProvider>
            <SignOutGuard />
            {children}
          </ToastProvider>
        </body>
      </html>
    </ClerkProvider>
  );
}
