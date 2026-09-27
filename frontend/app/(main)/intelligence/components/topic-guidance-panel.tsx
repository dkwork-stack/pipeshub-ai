'use client';

import { useEffect, useState } from 'react';
import { Button, Flex, Select, Text, TextArea, TextField } from '@radix-ui/themes';
import { mergeTopic, updateTopic, useTopics } from '../api';
import type { IntelligenceTopic } from '../types';
import { EmptyState, ErrorState } from './states';

export function TopicGuidancePanel({
  kind,
  canonicalName,
}: {
  kind: 'pain_point' | 'feature_gap';
  canonicalName: string;
}) {
  const { data: topics, error, mutate } = useTopics(kind);
  const topic = (topics ?? []).find((t) => t.canonical_name === canonicalName) ?? null;

  const [guidance, setGuidance] = useState('');
  const [aliasesText, setAliasesText] = useState('');
  const [mergeTargetId, setMergeTargetId] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!topic) return;
    setGuidance(topic.guidance ?? '');
    setAliasesText((topic.aliases ?? []).join(', '));
  }, [topic]);

  if (error) return <ErrorState error={error} onRetry={() => void mutate()} />;
  if (!topics) return null;
  if (!topic) {
    return (
      <EmptyState
        icon="tune"
        title="No taxonomy topic yet"
        description="This name will appear here after the next ingestion creates a topic for it."
      />
    );
  }

  const others = topics.filter((t) => t.id !== topic.id);

  const onSave = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const aliases = aliasesText
        .split(',')
        .map((a) => a.trim())
        .filter(Boolean);
      await updateTopic(topic.id, { guidance: guidance || null, aliases });
      await mutate();
      setMessage('Saved.');
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const onMerge = async () => {
    if (!mergeTargetId) return;
    setSaving(true);
    setMessage(null);
    try {
      await mergeTopic(topic.id, Number(mergeTargetId));
      await mutate();
      setMessage('Merged.');
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Merge failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Flex direction="column" gap="3">
      <Text size="2" style={{ color: 'var(--slate-11)' }}>
        Tell the extractor what belongs under <strong>{topic.canonical_name}</strong>. Lines starting
        with <code>exclude:</code> or <code>ignore:</code> drop matching items after extraction.
      </Text>
      <TextArea
        rows={5}
        value={guidance}
        onChange={(e) => setGuidance(e.target.value)}
        placeholder={'Include Okta / SAML SSO.\nexclude: generic login bugs'}
      />
      <Flex direction="column" gap="1">
        <Text size="1" weight="medium">
          Aliases (comma-separated)
        </Text>
        <TextField.Root
          value={aliasesText}
          onChange={(e) => setAliasesText(e.target.value)}
          placeholder="SAML login, single sign-on"
        />
      </Flex>
      <Flex align="center" gap="2" wrap="wrap">
        <Button size="1" color="blue" onClick={() => void onSave()} disabled={saving}>
          Save guidance
        </Button>
        {others.length > 0 ? (
          <>
            <Select.Root size="1" value={mergeTargetId || '__none__'} onValueChange={(v) => setMergeTargetId(v === '__none__' ? '' : v)}>
              <Select.Trigger placeholder="Merge into…" style={{ minWidth: 180 }} />
              <Select.Content>
                <Select.Item value="__none__">Merge into…</Select.Item>
                {others.map((t: IntelligenceTopic) => (
                  <Select.Item key={t.id} value={String(t.id)}>
                    {t.canonical_name}
                  </Select.Item>
                ))}
              </Select.Content>
            </Select.Root>
            <Button size="1" variant="soft" color="blue" onClick={() => void onMerge()} disabled={saving || !mergeTargetId}>
              Merge
            </Button>
          </>
        ) : null}
        {message ? (
          <Text size="1" style={{ color: 'var(--slate-11)' }}>
            {message}
          </Text>
        ) : null}
      </Flex>
    </Flex>
  );
}
