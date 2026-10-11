const MIN_PRICE = 0.001;

export function parsePrice(header: string): number | null {
  if (!header) return null;
  const parts = header.trim().split(/\s+/);
  if (parts.length !== 2) return null;
  const [currency, amountStr] = parts;
  if (currency.toUpperCase() !== 'USD') return null;
  const amount = parseFloat(amountStr);
  if (isNaN(amount) || amount < MIN_PRICE) return null;
  return Math.round(amount * 10000) / 10000;
}

export function formatPrice(price: number): string {
  return `USD ${price.toFixed(4).replace(/\.?0+$/, '')}`;
}

export function isPriceAcceptable(offeredPrice: number, configuredPrice: number): boolean {
  return offeredPrice >= configuredPrice;
}
