export function formatMicrodollars(amount: bigint): string {
  const dollars = Number(amount) / 1_000_000;
  // Show sub-cent precision when needed (e.g. "$0.008"), otherwise 2 decimals
  if (dollars === 0) return "$0.00";
  const abs = Math.abs(dollars);
  const decimals = abs < 0.01 ? 3 : 2;
  const sign = dollars < 0 ? "-" : "";
  return `${sign}$${abs.toFixed(decimals)}`;
}

export function centsToMicrodollars(cents: number): bigint {
  return BigInt(cents) * BigInt(10000);
}

export function microdollarsToCents(microdollars: bigint): number {
  return Number(microdollars / BigInt(10000));
}
