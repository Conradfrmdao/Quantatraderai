export type VenueGuide = {
  slug: string;
  venueType: string;
  name: string;
  summary: string;
  startMode: string;
  whereToCreate: string[];
  requiredFields: string[];
  enablePermissions: string[];
  avoidPermissions: string[];
  ipWhitelist: string;
  sandbox: string;
  revoke: string;
};

export const VENUE_GUIDES: VenueGuide[] = [
  {
    slug: "binance",
    venueType: "BINANCE",
    name: "Binance",
    summary: "Spot and futures API keys for crypto trading.",
    startMode: "Start in paper mode first, then enable live trading only after you trust the receipts and reconciliation.",
    whereToCreate: [
      "Log in to Binance and open API Management from your account settings.",
      "Create a new API key and complete Binance security verification.",
    ],
    requiredFields: ["API Key", "API Secret", "Market mode: spot or futures"],
    enablePermissions: [
      "Enable Reading.",
      "Enable Spot & Margin Trading only if you need spot execution.",
      "Enable Futures only if you plan to trade futures.",
    ],
    avoidPermissions: ["Never enable Withdrawals.", "Do not share keys outside your trusted server."],
    ipWhitelist: "Strongly recommended. Restrict the key to your server IP before going live.",
    sandbox: "Use paper mode in QuantatraderAI first. Binance testnet can help, but paper mode is the safest first step.",
    revoke: "Delete or disable the API key from Binance API Management immediately if you suspect exposure.",
  },
  {
    slug: "oanda",
    venueType: "OANDA",
    name: "OANDA",
    summary: "v20 API token setup for forex trading.",
    startMode: "Start in QuantatraderAI paper mode first, then use an OANDA practice account before switching the venue to live.",
    whereToCreate: [
      "Create or log in to an OANDA practice or live account.",
      "Open Manage API Access and generate a v20 API token.",
    ],
    requiredFields: ["Account ID", "API Token", "Environment: practice or live"],
    enablePermissions: ["Use the correct practice or live environment.", "Confirm the account ID matches the token environment."],
    avoidPermissions: ["Do not paste a live token into a practice configuration.", "Do not share the token in screenshots or chat logs."],
    ipWhitelist: "Not required by OANDA, but keep the token only on your trusted server.",
    sandbox: "OANDA practice accounts are the recommended sandbox.",
    revoke: "Revoke the token from OANDA API access settings and generate a new one if needed.",
  },
  {
    slug: "metatrader",
    venueType: "METATRADER",
    name: "MetaTrader / MetaApi",
    summary: "Connect an MT4 or MT5 broker account through MetaApi.",
    startMode: "Start in paper mode first, then use a demo broker account linked through MetaApi before going live.",
    whereToCreate: [
      "Create a MetaApi account.",
      "Connect your MT4 or MT5 broker account inside MetaApi.",
    ],
    requiredFields: ["MetaApi Token", "MetaApi Account ID"],
    enablePermissions: ["Keep the MetaApi account connected and healthy.", "Verify the broker account is the intended demo or live account."],
    avoidPermissions: ["Do not paste raw broker passwords into QuantatraderAI.", "Do not expose the MetaApi token publicly."],
    ipWhitelist: "MetaApi manages the bridge, so IP whitelist is not typically used here.",
    sandbox: "Use a demo MT4 or MT5 broker account first.",
    revoke: "Revoke the MetaApi token from MetaApi dashboard and disconnect the trading account if required.",
  },
  {
    slug: "hyperliquid",
    venueType: "HYPERLIQUID",
    name: "Hyperliquid",
    summary: "Private key style API auth for Hyperliquid.",
    startMode: "Paper mode first. Only move to live after you verify position sync and receipts.",
    whereToCreate: [
      "Create an API wallet or signing key from your Hyperliquid account tools.",
      "Store the private key securely before connecting QuantatraderAI.",
    ],
    requiredFields: ["Wallet/API private key", "Optional network selection if required"],
    enablePermissions: ["Use the minimum key scope required for trading.", "Keep the wallet funded conservatively while testing."],
    avoidPermissions: ["Never reuse a wallet key that also controls large funds elsewhere.", "Never expose the private key in browser tools or screenshots."],
    ipWhitelist: "Use Hyperliquid account-level protections where available; otherwise protect access at the server layer.",
    sandbox: "Use paper mode in QuantatraderAI if you do not have a safe isolated test wallet.",
    revoke: "Rotate or delete the wallet/API key from Hyperliquid account settings.",
  },
  {
    slug: "bybit",
    venueType: "BYBIT",
    name: "Bybit",
    summary: "API key setup for spot and derivatives on Bybit.",
    startMode: "Use Bybit demo or QuantatraderAI paper mode first.",
    whereToCreate: ["Open Bybit API Management.", "Create a new API key with the trading scopes you need."],
    requiredFields: ["API Key", "API Secret", "Optional passphrase if required by your account flow"],
    enablePermissions: ["Enable Read access.", "Enable Trading only for the markets you actually use."],
    avoidPermissions: ["Never enable withdrawals.", "Avoid broad unrestricted permissions."],
    ipWhitelist: "Recommended before live trading.",
    sandbox: "Bybit demo plus QuantatraderAI paper mode is the safest start.",
    revoke: "Disable or delete the key in Bybit API Management.",
  },
  {
    slug: "okx",
    venueType: "OKX",
    name: "OKX",
    summary: "API key, secret, and passphrase setup for OKX.",
    startMode: "Start in paper mode first.",
    whereToCreate: ["Create an API key in OKX security settings."],
    requiredFields: ["API Key", "API Secret", "Passphrase"],
    enablePermissions: ["Enable Read.", "Enable Trade."],
    avoidPermissions: ["Never enable withdrawals."],
    ipWhitelist: "Recommended for any live key.",
    sandbox: "Use OKX demo trading or QuantatraderAI paper mode first.",
    revoke: "Delete the key from OKX security settings.",
  },
  {
    slug: "kraken",
    venueType: "KRAKEN",
    name: "Kraken",
    summary: "Exchange API key setup for Kraken.",
    startMode: "Start in paper mode before enabling live execution.",
    whereToCreate: ["Open Kraken API settings and create a new key."],
    requiredFields: ["API Key", "API Secret"],
    enablePermissions: ["Enable Query Funds or equivalent read scopes.", "Enable Order and trade scopes only if you want live execution."],
    avoidPermissions: ["Do not enable withdrawal scopes."],
    ipWhitelist: "Recommended when available for your Kraken key.",
    sandbox: "QuantatraderAI paper mode is the safest first step.",
    revoke: "Disable or remove the key from Kraken API settings.",
  },
  {
    slug: "coinbase",
    venueType: "COINBASE",
    name: "Coinbase Advanced",
    summary: "API key setup for Coinbase trading accounts.",
    startMode: "Use paper mode first and validate reconciliation before going live.",
    whereToCreate: ["Create a trading API key in Coinbase Advanced or Coinbase Developer settings."],
    requiredFields: ["API Key", "API Secret", "Passphrase if Coinbase requires it for your key type"],
    enablePermissions: ["Enable portfolio read access.", "Enable trading scopes only for the account you intend to automate."],
    avoidPermissions: ["Never enable withdrawal or transfer permissions if present."],
    ipWhitelist: "Recommended for live automation keys.",
    sandbox: "Use paper mode first if you do not have a Coinbase sandbox setup.",
    revoke: "Delete the key from Coinbase API settings immediately if compromised.",
  },
  {
    slug: "alpaca",
    venueType: "ALPACA",
    name: "Alpaca",
    summary: "Stocks API keys for Alpaca live or paper accounts.",
    startMode: "Start in paper mode first, then move to Alpaca paper trading before live execution.",
    whereToCreate: ["Open Alpaca dashboard and create API keys for either paper or live trading."],
    requiredFields: ["API Key", "API Secret", "Paper or live account selection"],
    enablePermissions: ["Use paper keys first.", "Keep live capital small until receipts and positions are proven correct."],
    avoidPermissions: ["Do not mix live keys into a paper environment.", "Do not store screenshots of your secret key."],
    ipWhitelist: "Not always required, but keep the keys only on your trusted server.",
    sandbox: "Alpaca paper trading is the recommended sandbox.",
    revoke: "Revoke the keys from the Alpaca dashboard and generate a new pair.",
  },
  {
    slug: "ibkr",
    venueType: "IBKR",
    name: "Interactive Brokers",
    summary: "Connect IBKR through TWS or IB Gateway.",
    startMode: "Start in paper mode first, then use an IBKR paper account or demo workflow before going live.",
    whereToCreate: [
      "Set up Trader Workstation or IB Gateway.",
      "Enable API access in IBKR settings and note the host, port, and client ID.",
    ],
    requiredFields: ["Host", "Port", "Client ID"],
    enablePermissions: ["Enable API connections.", "Use the paper trading account first."],
    avoidPermissions: ["Do not point production automation at the wrong live account.", "Do not expose TWS credentials in QuantatraderAI."],
    ipWhitelist: "Use TWS or network restrictions if your deployment allows it.",
    sandbox: "IBKR paper trading is the recommended sandbox.",
    revoke: "Disable API access in TWS or IB Gateway and rotate client configuration if needed.",
  },
  {
    slug: "polymarket",
    venueType: "POLYMARKET",
    name: "Polymarket",
    summary: "Prediction market access with a private key or signing wallet.",
    startMode: "Use a low-risk wallet or paper mode first.",
    whereToCreate: ["Create or choose the wallet/key used for Polymarket API access."],
    requiredFields: ["Private key or signing credential", "Network configuration if required"],
    enablePermissions: ["Use a dedicated low-risk key if possible."],
    avoidPermissions: ["Do not reuse a high-value wallet.", "Never expose the private key in browser logs or screenshots."],
    ipWhitelist: "Protect at the server layer if venue-level IP whitelist is unavailable.",
    sandbox: "Use paper mode first if you do not have an isolated test wallet.",
    revoke: "Rotate the wallet/key immediately if you suspect exposure.",
  },
];

export function getVenueGuide(slug: string): VenueGuide | undefined {
  return VENUE_GUIDES.find((guide) => guide.slug === slug);
}
