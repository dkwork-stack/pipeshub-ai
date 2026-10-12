'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { AlertDialog, Button, Flex, Text, TextField } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import { useToastStore } from '@/lib/store/toast-store';
import { getUserFacingErrorMessage } from '@/lib/api/api-error';
import { eraseCustomer } from '../api';
import { portal } from './theme';

/**
 * GDPR right-to-erasure for one customer: removes the customer, every piece
 * of evidence and its revenue history. Irreversible, so the user types the
 * customer name to confirm; the server writes an audit entry.
 */
export function EraseCustomerButton({ customerId, customerName }: { customerId: string; customerName: string }) {
  const router = useRouter();
  const addToast = useToastStore((s) => s.addToast);
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState('');
  const [busy, setBusy] = useState(false);
  const confirmed = typed.trim() === customerName.trim();

  const onConfirm = async () => {
    if (!confirmed || busy) return;
    setBusy(true);
    try {
      const result = await eraseCustomer(customerId);
      setOpen(false);
      addToast({
        variant: 'success',
        title: `${customerName} erased`,
        description: `${result.feature_gap_mentions + result.pain_point_mentions} evidence item(s) and ${result.revenue_snapshots} revenue snapshot(s) removed.`,
        duration: 5000,
      });
      router.push('/intelligence/customers');
    } catch (error) {
      addToast({
        variant: 'error',
        title: 'Erasure failed',
        description: getUserFacingErrorMessage(error, 'You may need the intelligence:write permission.'),
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <AlertDialog.Root
      open={open}
      onOpenChange={(next) => {
        if (busy) return;
        setOpen(next);
        if (!next) setTyped('');
      }}
    >
      <AlertDialog.Trigger>
        <Button size="2" variant="soft" color="red">
          <MaterialIcon name="delete_forever" size={16} /> Erase customer data
        </Button>
      </AlertDialog.Trigger>
      <AlertDialog.Content style={{ maxWidth: 480 }}>
        <AlertDialog.Title>Erase {customerName}?</AlertDialog.Title>
        <AlertDialog.Description size="2">
          This permanently deletes the customer, all of its pain points, feature requests, quotes and revenue history
          from Customer Intelligence, and recomputes every affected score. Source records in connected systems are not
          touched. The erasure is recorded in the audit log.
        </AlertDialog.Description>
        <Flex direction="column" gap="1" mt="4">
          <Text size="2" style={{ color: portal.strong }}>
            Type <Text weight="bold">{customerName}</Text> to confirm
          </Text>
          <TextField.Root value={typed} onChange={(e) => setTyped(e.target.value)} disabled={busy} autoFocus />
        </Flex>
        <Flex gap="3" mt="5" justify="end">
          <AlertDialog.Cancel>
            <Button variant="soft" color="gray" disabled={busy}>
              Cancel
            </Button>
          </AlertDialog.Cancel>
          <Button color="red" disabled={!confirmed || busy} loading={busy} onClick={() => void onConfirm()}>
            Erase permanently
          </Button>
        </Flex>
      </AlertDialog.Content>
    </AlertDialog.Root>
  );
}
