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
  themeColor: "#000000",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider afterSignOutUrl="/">
      <html lang="en" className="h-full">
        <head>
          <link rel="icon"             href="/favicon.ico"           sizes="any" />
          <link rel="icon"             href="/icon.svg"              type="image/svg+xml" />
          <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
          <link rel="manifest"         href="/site.webmanifest" />
        </head>
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
