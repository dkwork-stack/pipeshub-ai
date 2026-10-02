'use client';

import { useEffect, useState } from 'react';
import { Button, Flex, Select, Text, TextArea, TextField } from '@radix-ui/themes';
import { mergeTopic, updateTopic, useTopics } from '../api';
import type { IntelligenceTopic } from '../types';
import { EmptyState, ErrorState } from './states';
import { portal } from './theme';

const filterControlStyle = {
  ...portal.input,
  height: portal.control.height,
  minHeight: portal.control.height,
  display: 'inline-flex',
  alignItems: 'center',
} as const;

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
      <Text size="2" style={{ color: portal.muted }}>
        Tell the extractor what belongs under <strong>{topic.canonical_name}</strong>. Lines starting
        with <code>exclude:</code> or <code>ignore:</code> drop matching items after extraction.
      </Text>
      <TextArea
        size="3"
        rows={5}
        value={guidance}
        onChange={(e) => setGuidance(e.target.value)}
        placeholder={'Include Okta / SAML SSO.\nexclude: generic login bugs'}
        style={portal.textarea}
      />
      <Flex direction="column" gap="1" className="intelligence-filters">
        <Text size="2" weight="medium" style={{ color: portal.strong }}>
          Aliases (comma-separated)
        </Text>
        <TextField.Root
          size="3"
          value={aliasesText}
          onChange={(e) => setAliasesText(e.target.value)}
          placeholder="SAML login, single sign-on"
          style={{ width: '100%', ...filterControlStyle }}
        />
      </Flex>
      <Flex align="center" gap="3" wrap="wrap">
        <Button
          size="2"
          onClick={() => void onSave()}
          disabled={saving}
          style={{
            ...portal.button.primary,
            minHeight: portal.control.height,
            paddingLeft: 16,
            paddingRight: 16,
          }}
        >
          Save guidance
        </Button>
        {message ? (
          <Text size="2" style={{ color: portal.muted }}>
            {message}
          </Text>
        ) : null}
      </Flex>

      {others.length > 0 ? (
        <Flex
          direction="column"
          gap="2"
          className="intelligence-filters"
          style={{
            marginTop: 4,
            padding: '14px 16px',
            borderRadius: 10,
            border: `1px solid ${portal.colors.border}`,
            backgroundColor: portal.colors.tableHeaderBg,
          }}
        >
          <Text size="2" weight="medium" style={{ color: portal.strong }}>
            Merge into another topic
          </Text>
          <Text size="1" style={{ color: portal.muted }}>
            Fold this topic into an existing one. Mentions and aliases move to the target.
          </Text>
          <Flex align="center" gap="3" wrap="wrap">
            <Select.Root
              size="3"
              value={mergeTargetId || '__none__'}
              onValueChange={(v) => setMergeTargetId(v === '__none__' ? '' : v)}
            >
              <Select.Trigger placeholder="Choose topic…" style={{ minWidth: 220, ...filterControlStyle }} />
              <Select.Content className="intelligence-select-content" position="popper">
                <Select.Item value="__none__">Choose topic…</Select.Item>
                {others.map((t: IntelligenceTopic) => (
                  <Select.Item key={t.id} value={String(t.id)}>
                    {t.canonical_name}
                  </Select.Item>
                ))}
              </Select.Content>
            </Select.Root>
            <Button
              size="2"
              variant="soft"
              onClick={() => void onMerge()}
              disabled={saving || !mergeTargetId}
              style={{
                ...portal.button.secondary,
                minHeight: portal.control.height,
                paddingLeft: 16,
                paddingRight: 16,
              }}
            >
              Merge
            </Button>
          </Flex>
        </Flex>
      ) : null}
    </Flex>
  );
}
