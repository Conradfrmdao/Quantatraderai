import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import { ToastProvider } from "@/components/Toast";
import { SignOutGuard } from "@/components/SignOutGuard";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "QuantaTrade AI — The AI Agent That Trades While You Sleep",
  description: "Multi-venue AI trading agent. Connects to Hyperliquid, Binance, OANDA, MetaTrader, Alpaca, IBKR and 100+ exchanges. 24/7 autonomous trading with collective AI council decision-making.",
  icons: { icon: "/icon.svg" },
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
