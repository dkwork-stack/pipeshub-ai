'use client';

import Link from 'next/link';
import { DropdownMenu, IconButton } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import { portal } from './theme';

/** Per-row "⋮" menu — currently just a shortcut to the detail page. */
export function RowMenu({ detailHref, label }: { detailHref: string; label?: string }) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger>
        <IconButton variant="ghost" color="gray" size="1" aria-label="Row actions">
          <MaterialIcon name="more_vert" size={18} color={portal.muted} />
        </IconButton>
      </DropdownMenu.Trigger>
      <DropdownMenu.Content align="end">
        <DropdownMenu.Item asChild>
          <Link href={detailHref}>{label ?? 'View details'}</Link>
        </DropdownMenu.Item>
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
}
