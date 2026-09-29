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
  } as const,
  panel: {
    backgroundColor: '#ffffff',
    border: '1px solid #e8edf5',
    borderRadius: 12,
    // Soft elevation so cards lift off the white page without looking heavy.
    boxShadow: '0 1px 2px rgba(23, 32, 51, 0.04), 0 6px 16px rgba(23, 32, 51, 0.06)',
  } as const,
  sidebar: {
    width: 244,
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
  } as const,
  muted: '#667085',
  strong: '#172033',
  accent: '#2563eb',
  /** Single source of truth for product branding — update here, not per-component. */
  brand: {
    name: 'Cooper',
    tagline: 'Feature Intelligence',
    icon: 'auto_awesome',
    gradient: 'linear-gradient(145deg, #2563eb, #1d4ed8)',
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
