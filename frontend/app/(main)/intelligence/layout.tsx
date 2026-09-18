'use client';

import { PortalShell } from './components/shell';

export default function IntelligenceLayout({ children }: { children: React.ReactNode }) {
  return <PortalShell>{children}</PortalShell>;
}
