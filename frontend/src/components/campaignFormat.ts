/** Formatting helpers for campaign values: absent means "not computed", never zero. */

export const DASH = '—';

export function fmt(value: number | null | undefined, digits = 2): string {
  return value === null || value === undefined || Number.isNaN(value) ? DASH : value.toFixed(digits);
}

export function fmtSigned(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  return `${value > 0 ? '+' : ''}${value.toFixed(digits)}`;
}

export function currentYear(): number {
  return new Date().getFullYear();
}

export function shortParcelId(id: string): string {
  return id.includes(':') ? id.split(':').pop() || id : id;
}
