/**
 * Shared visual tokens for the Cooper customer intelligence portal.
 * Palette, radii, and layout are pinned to the approved Cooper mocks
 * (cooper-overview/feature-gaps/pain-points/customers) — update here, not
 * per-component, so every page stays in sync.
 */

export const portal = {
  pageBg: '#ffffff',
  contentMaxWidth: 1180,
  displayFont: "'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  colors: {
    text: '#172033',
    muted: '#667085',
    blue: '#2563eb',
    blueHover: '#1d4ed8',
    blueSoftBg: '#eff6ff',
    border: '#e8edf5',
    tableHeaderBg: '#f8fafc',
    /** Column headers — pinned dark so Radix olive gray can't wash them out. */
    tableHeaderText: '#0f172a',
  } as const,
  tableHeader: {
    color: '#0f172a',
    fontWeight: 600,
    fontSize: 12,
    letterSpacing: '0.01em',
  } as const,
  panel: {
    backgroundColor: '#ffffff',
    border: '1px solid #e8edf5',
    borderRadius: 12,
    // Soft elevation so cards lift off the white page without looking heavy.
    boxShadow: '0 1px 2px rgba(23, 32, 51, 0.04), 0 6px 16px rgba(23, 32, 51, 0.06)',
  } as const,
  sidebar: {
    collapsedWidth: 72,
    expandedWidth: 244,
    backgroundColor: '#2563eb',
    border: '#1d4ed8',
    text: '#ffffff',
    muted: 'rgba(255, 255, 255, 0.85)',
    activeBg: 'rgba(255, 255, 255, 0.22)',
  } as const,
  /** Inline style overrides — Radix's built-in `color="blue"` scale doesn't
   *  match the mock's exact hex, so buttons apply these directly. */
  button: {
    primary: { backgroundColor: '#2563eb', color: '#ffffff', borderRadius: 8, fontWeight: 600 } as const,
    secondary: { backgroundColor: '#eff6ff', color: '#2563eb', borderRadius: 8, fontWeight: 600 } as const,
  } as const,
  /**
   * The app's global theme (`grayColor="olive"`, see theme-provider.tsx) makes
   * Radix's default TextField/Select "surface" fill render as a flat mid-gray
   * block instead of white — looks disabled. Override explicitly for inputs
   * in this portal. Radix draws its border as an inset box-shadow, not a real
   * `border`, so we replace that too.
   */
  input: {
    backgroundColor: '#ffffff',
    boxShadow: 'inset 0 0 0 1px #e8edf5',
    color: '#172033',
    height: 44,
    minHeight: 44,
    boxSizing: 'border-box' as const,
  } as const,
  /** TextArea shares the input chrome but must not inherit the fixed 44px control height. */
  textarea: {
    backgroundColor: '#ffffff',
    boxShadow: 'inset 0 0 0 1px #e8edf5',
    color: '#172033',
    minHeight: 120,
    boxSizing: 'border-box' as const,
  } as const,
  control: {
    height: 44,
  } as const,
  muted: '#667085',
  strong: '#172033',
  accent: '#2563eb',
  /** Single source of truth for product branding — update here, not per-component. */
  brand: {
    name: 'Cooper',
    tagline: 'Feature demand & evidence',
    logoSrc: '/icons/cooper-logo.png',
  } as const,
  /**
   * Pastel icon-badge colors for stat cards (StatStrip). Every value shown
   * with these must be real — no stat card renders a number we can't back
   * with an actual API field.
   */
  statPalette: {
    green: { bg: '#dcfce7', fg: '#16a34a' },
    purple: { bg: '#f3e8ff', fg: '#9333ea' },
    amber: { bg: '#fef3c7', fg: '#d97706' },
    blue: { bg: '#dbeafe', fg: '#2563eb' },
    pink: { bg: '#fce7f3', fg: '#db2777' },
    red: { bg: '#fee2e2', fg: '#dc2626' },
  } as const,
  /** Semantic score/confidence coloring — green above threshold, amber below. */
  semantic: {
    good: { bg: '#dcfce7', fg: '#15803d' },
    warn: { bg: '#fef3c7', fg: '#b45309' },
  } as const,
  /** Deterministic avatar palette — color is picked by hashing the name, not random. */
  avatarPalette: ['#2563eb', '#9333ea', '#ea580c', '#0f172a', '#0891b2', '#16a34a', '#db2777', '#4f46e5'],
} as const;
