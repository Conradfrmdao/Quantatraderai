import Link from "next/link";
import { notFound } from "next/navigation";

import { getVenueGuide, VENUE_GUIDES } from "@/lib/venue-guides";

export function generateStaticParams() {
  return VENUE_GUIDES.map((guide) => ({ venue: guide.slug }));
}

function ListSection({ title, items }: { title: string; items: string[] }) {
  return (
    <section style={{ marginBottom: 24 }}>
      <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 10 }}>{title}</h2>
      <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 8 }}>
        {items.map((item) => (
          <li
            key={item}
            style={{
              background: "rgba(255,255,255,0.03)",
              border: "1px solid rgba(255,255,255,0.07)",
              borderRadius: 12,
              padding: "12px 14px",
              fontSize: 13,
              color: "rgba(255,255,255,0.62)",
              lineHeight: 1.6,
            }}
          >
            {item}
          </li>
        ))}
      </ul>
    </section>
  );
}

export default async function VenueApiKeyGuidePage({ params }: { params: Promise<{ venue: string }> }) {
  const { venue } = await params;
  const guide = getVenueGuide(venue);
  if (!guide) notFound();

  return (
    <div style={{ minHeight: "100vh", background: "#080808", color: "#fff", padding: "32px 20px" }}>
      <div style={{ maxWidth: 880, margin: "0 auto" }}>
        <Link href="/docs/api-keys" style={{ color: "rgba(255,255,255,0.4)", textDecoration: "none", fontSize: 13 }}>
          ← Back to API Key Guides
        </Link>

        <div style={{ margin: "18px 0 24px" }}>
          <div style={{ fontSize: 11, color: "#4ade80", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 10 }}>
            {guide.venueType}
          </div>
          <h1 style={{ fontSize: 34, fontWeight: 800, marginBottom: 10 }}>{guide.name}</h1>
          <p style={{ fontSize: 15, color: "rgba(255,255,255,0.55)", lineHeight: 1.7, marginBottom: 12 }}>
            {guide.summary}
          </p>
          <div style={{ background: "rgba(251,191,36,0.08)", border: "1px solid rgba(251,191,36,0.2)", borderRadius: 14, padding: "12px 14px", fontSize: 13, color: "#fcd34d", lineHeight: 1.6 }}>
            {guide.startMode}
          </div>
        </div>

        <div style={{ display: "grid", gap: 22 }}>
          <ListSection title="Where To Create It" items={guide.whereToCreate} />
          <ListSection title="Fields QuantatraderAI Needs" items={guide.requiredFields} />
          <ListSection title="Permissions To Enable" items={guide.enablePermissions} />
          <ListSection title="Permissions To Avoid" items={guide.avoidPermissions} />

          <section style={{ display: "grid", gap: 14 }}>
            <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 14, padding: "14px 16px" }}>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 8 }}>IP Whitelist Guidance</h2>
              <p style={{ fontSize: 13, color: "rgba(255,255,255,0.62)", lineHeight: 1.6 }}>{guide.ipWhitelist}</p>
            </div>
            <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 14, padding: "14px 16px" }}>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 8 }}>Sandbox / Test Mode</h2>
              <p style={{ fontSize: 13, color: "rgba(255,255,255,0.62)", lineHeight: 1.6 }}>{guide.sandbox}</p>
            </div>
            <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 14, padding: "14px 16px" }}>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 8 }}>How To Revoke It</h2>
              <p style={{ fontSize: 13, color: "rgba(255,255,255,0.62)", lineHeight: 1.6 }}>{guide.revoke}</p>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
