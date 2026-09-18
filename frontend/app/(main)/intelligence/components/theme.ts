/** Shared visual tokens for the intelligence portal (Freshservice-inspired, PipesHub palette). */

export const portal = {
  pageBg:
    'radial-gradient(1200px 480px at 12% -10%, rgba(18, 249, 157, 0.14), transparent 55%), radial-gradient(900px 420px at 88% 0%, rgba(4, 120, 87, 0.08), transparent 50%), linear-gradient(180deg, #f5fefb 0%, #f7f8f7 42%, #f4f5f4 100%)',
  contentMaxWidth: 1180,
  displayFont: 'ClashGrotesk, Manrope, sans-serif',
  panel: {
    backgroundColor: 'rgba(255, 255, 255, 0.92)',
    border: '1px solid var(--slate-5)',
    borderRadius: 16,
    boxShadow: '0 1px 2px rgba(15, 61, 44, 0.04), 0 8px 24px rgba(15, 61, 44, 0.04)',
  } as const,
  navPill: {
    height: 36,
    borderRadius: 999,
    padding: '0 14px',
  } as const,
  muted: 'var(--slate-11)',
  strong: 'var(--slate-12)',
  accent: 'var(--accent-9)',
} as const;
