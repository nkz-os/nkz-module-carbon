/** Design token CSS variable references for inline styles.
 *
 * Prefer nkz-* CSS classes over inline styles when possible.
 * These constants are for cases where inline styles are unavoidable
 * (e.g. dynamic styles, component library integration gaps).
 */
export const colors = {
  textPrimary: 'var(--nkz-text-primary, #111827)',
  textSecondary: 'var(--nkz-text-secondary, #6B7280)',
  textMuted: 'var(--nkz-text-muted, #9CA3AF)',
  accentBase: 'var(--nkz-accent-base, #059669)',
  accentSoft: 'var(--nkz-accent-soft, #F0FDF4)',
  accentStrong: 'var(--nkz-accent-strong, #14532D)',
  danger: 'var(--nkz-danger, #DC2626)',
  border: 'var(--nkz-border, #E5E7EB)',
  bgSurface: 'var(--nkz-bg-surface, #FFFFFF)',
  bgSubtle: 'var(--nkz-bg-subtle, #F9FAFB)',
  bgMuted: 'var(--nkz-bg-muted, #F3F4F6)',
  blue: 'var(--nkz-blue-600, #2563EB)',
  gray300: 'var(--nkz-gray-300, #D1D5DB)',
} as const;
