/** Shared visual tokens for the Cooper customer intelligence portal. */

export const portal = {
  pageBg: '#ffffff',
  contentMaxWidth: 1180,
  displayFont: 'ClashGrotesk, Manrope, sans-serif',
  panel: {
    backgroundColor: '#ffffff',
    border: '1px solid var(--slate-4)',
    borderRadius: 16,
    boxShadow: '0 1px 2px rgba(15, 23, 42, 0.04), 0 6px 16px rgba(15, 23, 42, 0.05)',
  } as const,
  rail: {
    collapsedWidth: 76,
    expandedWidth: 244,
  } as const,
  muted: 'var(--slate-11)',
  strong: 'var(--slate-12)',
  accent: 'var(--blue-9)',
  /** Single source of truth for product branding — update here, not per-component. */
  brand: {
    name: 'Cooper',
    tagline: 'Feature Intelligence',
    icon: 'auto_awesome',
    gradient: 'linear-gradient(145deg, var(--blue-8), var(--blue-11))',
  } as const,
} as const;
