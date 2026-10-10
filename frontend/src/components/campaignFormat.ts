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

/** Unit line for production totals: says when they cover only part of the cycle days. */
export function productionUnit(unit: string, coverage: number | null | undefined,
                               t: (k: string, o?: Record<string, unknown>) => string): string {
  if (coverage === null || coverage === undefined || coverage >= 1) return unit;
  return `${unit} · ${t('partial_pct', { pct: Math.round(coverage * 100) })}`;
}
