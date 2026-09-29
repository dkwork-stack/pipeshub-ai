'use client';

import { Button } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import { portal } from './theme';

export function ExportButton({ onExport, disabled }: { onExport: () => void; disabled?: boolean }) {
  return (
    <Button
      size="1"
      variant="outline"
      onClick={onExport}
      disabled={disabled}
      style={{ ...portal.input, fontWeight: 600 }}
    >
      <MaterialIcon name="download" size={14} color={portal.strong} />
      Export
    </Button>
  );
}
