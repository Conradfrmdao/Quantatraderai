"use client";
import { useState, useEffect, useCallback } from "react";
import type { VenueCatalog, VenueCapability } from "@/lib/venue-capabilities";

export interface UserVenue {
  id: string;
  displayName: string;
  type: string;
  market: string;
  paperCapital: number;
  isPaper: boolean;
  isActive: boolean;
  network: string | null;
  ccxtExchangeId: string | null;
  capability?: VenueCapability;
}

interface VenuesResponse {
  venues?: UserVenue[];
  catalog?: VenueCatalog;
}

/** Fetches all venues the current user has configured plus the backend venue catalog. */
export function useVenues() {
  const [venues, setVenues] = useState<UserVenue[]>([]);
  const [catalog, setCatalog] = useState<VenueCatalog>({});
  const [loading, setLoading] = useState(true);

  const reload = useCallback(() => {
    setLoading(true);
    fetch("/api/venues", { credentials: "same-origin", cache: "no-store" })
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<VenuesResponse | UserVenue[]>;
      })
      .then((d) => {
        const payload = Array.isArray(d) ? { venues: d, catalog: {} } : d;
        setVenues(payload.venues ?? []);
        setCatalog(payload.catalog ?? {});
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  useEffect(() => { reload(); }, [reload]);

  return { venues, catalog, loading, reload };
}
