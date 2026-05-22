export const QUANT_WS_PROTOCOL = "quantatraderai-v1";
const QUANT_WS_AUTH_PREFIX = "auth.";

export function buildWebSocketConnection(url: string, token?: string | null): {
  url: string;
  protocols: string[];
} {
  const protocols = [QUANT_WS_PROTOCOL];
  const trimmedToken = token?.trim();
  if (trimmedToken) {
    protocols.push(`${QUANT_WS_AUTH_PREFIX}${trimmedToken}`);
  }
  return { url, protocols };
}
