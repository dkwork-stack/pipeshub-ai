'use client';

import { Button } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import { portal } from './theme';

export function ExportButton({ onExport, disabled }: { onExport: () => void; disabled?: boolean }) {
  return (
    <Button
      size="2"
      onClick={onExport}
      disabled={disabled}
      style={{
        ...portal.button.primary,
        minHeight: portal.control.height,
        paddingLeft: 14,
        paddingRight: 14,
        fontSize: 13,
      }}
    >
      <MaterialIcon name="download" size={16} color="#ffffff" />
      Export
    </Button>
  );
}
