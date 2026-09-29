'use client';

import { Button } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import { portal } from './theme';

export function ExportButton({ onExport, disabled }: { onExport: () => void; disabled?: boolean }) {
  return (
    <Button size="1" onClick={onExport} disabled={disabled} style={portal.button.primary}>
      <MaterialIcon name="download" size={14} color="#ffffff" />
      Export
    </Button>
  );
}
