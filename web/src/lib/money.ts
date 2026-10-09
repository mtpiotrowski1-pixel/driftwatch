// The API speaks integer minor units (cents); the UI speaks a decimal string.
// Keeping the conversion here means the rounding lives in one tested place.

export function centsToAmount(cents: number): string {
  return (cents / 100).toFixed(2);
}

export function amountToCents(amount: string): number {
  const value = Number.parseFloat(amount);
  if (!Number.isFinite(value) || value < 0) return 0;
  return Math.round(value * 100);
}

export function formatMoney(cents: number, currency: string): string {
  return `${centsToAmount(cents)} ${currency}`;
}
