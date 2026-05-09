import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { DisclaimerModal } from "@/components/DisclaimerModal";

export default async function ProtectedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { userId } = await auth();
  if (!userId) redirect("/sign-in");
  return (
    <>
      <DisclaimerModal />
      {children}
      <footer className="protected-footer" style={{
        borderTop: "1px solid rgba(255,255,255,0.04)",
        padding: "12px 20px",
        textAlign: "center",
        fontSize: 10,
        color: "rgba(255,255,255,0.18)",
        letterSpacing: "0.04em",
        background: "#080808",
      }}>
        QuantatraderAI is not a financial advisor. All AI decisions are informational only and do not
        constitute financial advice. Trading involves risk — never invest money you cannot afford to lose.
        Past performance does not guarantee future results.
      </footer>
    </>
  );
}
