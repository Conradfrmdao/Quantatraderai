export type VenueType =
  | "HYPERLIQUID" | "BINANCE" | "OANDA" | "POLYMARKET" | "CCXT"
  | "METATRADER" | "BYBIT" | "OKX" | "KRAKEN" | "COINBASE" | "ALPACA" | "IBKR";

export type VenueAssetClass = "crypto" | "forex" | "stocks" | "prediction";
export type VenueMarketMode = "spot" | "futures" | "forex" | "stocks" | "prediction";

export interface VenueOption {
  value: string;
  label: string;
}

export interface VenueFieldConfig {
  enabled: boolean;
  label?: string;
  placeholder?: string;
  secret?: boolean;
  options?: VenueOption[];
}

export interface VenueCapability {
  type: VenueType;
  registryName: string;
  label: string;
  shortLabel: string;
  description: string;
  assetClass: VenueAssetClass;
  assetLabel: string;
  supportsPaper: boolean;
  supportsLive: boolean;
  supportsBacktest: boolean;
  marketDataMode: "stream" | "polling";
  markets: Array<{ value: VenueMarketMode; label: string }>;
  defaultMarket: VenueMarketMode;
  symbols: {
    placeholder: string;
    acceptsManualEntry: boolean;
    formatHint: string;
    examples: string[];
    defaultSymbols: string[];
  };
  orderFeatures: {
    marketOrders: boolean;
    limitOrders: boolean;
    supportsLeverage: boolean;
    supportsShorting: boolean;
    supportsCloseAll: boolean;
  };
  auth: {
    apiKey: VenueFieldConfig;
    apiSecret: VenueFieldConfig;
    apiPassphrase: VenueFieldConfig;
    accountId: VenueFieldConfig;
    ccxtExchangeId: VenueFieldConfig;
    network: VenueFieldConfig;
    metaApiToken: VenueFieldConfig;
    metaApiAccountId: VenueFieldConfig;
  };
}

export type VenueCatalog = Record<string, VenueCapability>;

export interface VenueCatalogResponse<TVenue> {
  venues: TVenue[];
  catalog: VenueCatalog;
}

function inferAssetClass(type: string | null | undefined): VenueAssetClass {
  switch (type) {
    case "OANDA":
    case "METATRADER":
      return "forex";
    case "ALPACA":
    case "IBKR":
      return "stocks";
    case "POLYMARKET":
      return "prediction";
    default:
      return "crypto";
  }
}

function inferDefaultMarket(type: string | null | undefined): VenueMarketMode {
  switch (type) {
    case "HYPERLIQUID":
    case "BYBIT":
      return "futures";
    case "OANDA":
    case "METATRADER":
      return "forex";
    case "ALPACA":
    case "IBKR":
      return "stocks";
    case "POLYMARKET":
      return "prediction";
    default:
      return "spot";
  }
}

export function fallbackVenueCapability(type: string | null | undefined): VenueCapability {
  const assetClass = inferAssetClass(type);
  const defaultMarket = inferDefaultMarket(type);
  return {
    type: (type || "BINANCE") as VenueType,
    registryName: String(type || "binance").toLowerCase(),
    label: String(type || "BINANCE"),
    shortLabel: String(type || "BINANCE"),
    description: "Venue capability metadata unavailable.",
    assetClass,
    assetLabel: assetClass,
    supportsPaper: true,
    supportsLive: true,
    supportsBacktest: assetClass !== "prediction",
    marketDataMode: type === "BINANCE" ? "stream" : "polling",
    markets: [{ value: defaultMarket, label: defaultMarket[0].toUpperCase() + defaultMarket.slice(1) }],
    defaultMarket,
    symbols: {
      placeholder: assetClass === "forex" ? "EUR_USD" : assetClass === "stocks" ? "AAPL" : "BTC/USDT",
      acceptsManualEntry: true,
      formatHint: assetClass,
      examples: assetClass === "forex" ? ["EUR_USD"] : assetClass === "stocks" ? ["AAPL"] : ["BTC/USDT"],
      defaultSymbols: assetClass === "forex" ? ["EUR_USD"] : assetClass === "stocks" ? ["AAPL"] : ["BTC/USDT"],
    },
    orderFeatures: {
      marketOrders: true,
      limitOrders: false,
      supportsLeverage: defaultMarket === "futures" || defaultMarket === "forex",
      supportsShorting: defaultMarket === "futures" || defaultMarket === "forex",
      supportsCloseAll: true,
    },
    auth: {
      apiKey: { enabled: true, label: "API Key", placeholder: "API key", secret: true },
      apiSecret: { enabled: true, label: "API Secret", placeholder: "API secret", secret: true },
      apiPassphrase: { enabled: false },
      accountId: { enabled: false },
      ccxtExchangeId: { enabled: false },
      network: { enabled: false },
      metaApiToken: { enabled: false },
      metaApiAccountId: { enabled: false },
    },
  };
}

export function getVenueCapability(catalog: VenueCatalog | null | undefined, type: string | null | undefined): VenueCapability {
  return (type && catalog?.[type]) ? catalog[type] : fallbackVenueCapability(type);
}

export function normalizeCapabilityMarket(
  capability: VenueCapability | null | undefined,
  market: string | null | undefined,
): VenueMarketMode {
  const fallback = capability?.defaultMarket ?? "spot";
  const requested = String(market ?? "").toLowerCase();
  const allowed = new Set((capability?.markets ?? []).map((option) => option.value));
  return allowed.has(requested as VenueMarketMode)
    ? (requested as VenueMarketMode)
    : fallback;
}

export function capabilitySupportsEditableMarket(capability: VenueCapability | null | undefined): boolean {
  return (capability?.markets?.length ?? 0) > 1;
}
