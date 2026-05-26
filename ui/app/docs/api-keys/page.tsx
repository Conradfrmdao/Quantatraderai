import Link from "next/link";

import { VENUE_GUIDES } from "@/lib/venue-guides";

export default function ApiKeyGuideHubPage() {
  return (
    <div style={{ minHeight: "100vh", background: "#080808", color: "#fff", padding: "32px 20px" }}>
      <div style={{ maxWidth: 960, margin: "0 auto" }}>
        <div style={{ marginBottom: 28 }}>
          <Link href="/docs" style={{ color: "rgba(255,255,255,0.4)", textDecoration: "none", fontSize: 13 }}>
            ← Back to Docs
          </Link>
          <h1 style={{ fontSize: 34, fontWeight: 800, margin: "14px 0 10px" }}>API Key Guides</h1>
          <p style={{ fontSize: 15, color: "rgba(255,255,255,0.55)", maxWidth: 720, lineHeight: 1.7 }}>
            Beginner-safe setup instructions for every supported venue. Every guide tells you where to create
            the credentials, which permissions to enable, which permissions to avoid, how to revoke them, and why you should start in paper mode first.
          </p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 16 }}>
          {VENUE_GUIDES.map((guide) => (
            <Link
              key={guide.slug}
              href={`/docs/api-keys/${guide.slug}`}
              style={{
                textDecoration: "none",
                color: "inherit",
                background: "rgba(255,255,255,0.03)",
                border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: 16,
                padding: "18px 18px 20px",
              }}
            >
              <div style={{ fontSize: 11, color: "#4ade80", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 10 }}>
                {guide.venueType}
              </div>
              <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 8 }}>{guide.name}</h2>
              <p style={{ fontSize: 13, color: "rgba(255,255,255,0.52)", lineHeight: 1.6, marginBottom: 14 }}>
                {guide.summary}
              </p>
              <p style={{ fontSize: 12, color: "#fcd34d", lineHeight: 1.6 }}>
                {guide.startMode}
              </p>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
