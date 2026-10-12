'use client';

import { useState } from 'react';
import { Flex, Select, Text } from '@radix-ui/themes';
import { useToastStore } from '@/lib/store/toast-store';
import { getUserFacingErrorMessage } from '@/lib/api/api-error';
import { updateTopic, useTopics } from '../api';
import type { TopicStatus } from '../types';
import { STATUS_OPTIONS } from './signal-badges';
import { portal } from './theme';

/**
 * Lifecycle status of a topic (open → shipped). Writing it needs
 * `intelligence:write`; the server audits every change.
 */
export function StatusControl({
  kind,
  canonicalName,
  onChanged,
}: {
  kind: 'pain_point' | 'feature_gap';
  canonicalName: string;
  onChanged?: () => void;
}) {
  const { data: topics, mutate } = useTopics(kind);
  const addToast = useToastStore((s) => s.addToast);
  const [saving, setSaving] = useState(false);
  const topic = (topics ?? []).find((t) => t.canonical_name === canonicalName);
  if (!topic) return null;

  const onChange = async (value: string) => {
    setSaving(true);
    try {
      await updateTopic(topic.id, { status: value as TopicStatus });
      await mutate();
      onChanged?.();
      addToast({ variant: 'success', title: 'Status updated', duration: 3000 });
    } catch (error) {
      addToast({ variant: 'error', title: 'Could not update status', description: getUserFacingErrorMessage(error, 'Try again.') });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Flex align="center" gap="2">
      <Text size="1" weight="medium" style={{ color: portal.muted }}>
        Status
      </Text>
      <Select.Root size="2" value={topic.status ?? 'open'} onValueChange={(v) => void onChange(v)} disabled={saving}>
        <Select.Trigger style={{ ...portal.input, height: 36, minHeight: 36, minWidth: 150 }} />
        <Select.Content className="intelligence-select-content" position="popper">
          {STATUS_OPTIONS.map((o) => (
            <Select.Item key={o.value} value={o.value}>
              {o.label}
            </Select.Item>
          ))}
        </Select.Content>
      </Select.Root>
    </Flex>
  );
}
