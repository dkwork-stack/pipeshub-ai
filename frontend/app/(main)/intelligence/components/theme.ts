/**
 * Shared visual tokens for the Cooper customer intelligence portal.
 * Palette, radii, and button/card styling are pinned to blue-white-app.html
 * (root of the repo) — update there and mirror here, not per-component.
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
  } as const,
  panel: {
    backgroundColor: '#ffffff',
    border: '1px solid #e8edf5',
    borderRadius: 12,
    boxShadow: 'none',
  } as const,
  rail: {
    collapsedWidth: 76,
    expandedWidth: 244,
  } as const,
  /** Inline style overrides — Radix's built-in `color="blue"` scale doesn't
   *  match the mock's exact hex, so buttons apply these directly. */
  button: {
    primary: { backgroundColor: '#2563eb', color: '#ffffff', borderRadius: 8, fontWeight: 600 } as const,
    secondary: { backgroundColor: '#eff6ff', color: '#2563eb', borderRadius: 8, fontWeight: 600 } as const,
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
} as const;
