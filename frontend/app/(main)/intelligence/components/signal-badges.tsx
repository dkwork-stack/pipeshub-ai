'use client';

import { Badge, Flex, Text, Tooltip } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import type { EvidenceAttributes, TopicStatus } from '../types';
import { portal } from './theme';

type Tone = keyof typeof portal.signal;

const TONE: Record<string, { label: string; tone: Tone; icon: string }> = {
  frustrated: { label: 'Frustrated', tone: 'attention', icon: 'sentiment_dissatisfied' },
  angry: { label: 'Angry', tone: 'negative', icon: 'sentiment_very_dissatisfied' },
  anxious: { label: 'Anxious', tone: 'attention', icon: 'sentiment_worried' },
  neutral: { label: 'Neutral', tone: 'neutral', icon: 'sentiment_neutral' },
  appreciative: { label: 'Appreciative', tone: 'positive', icon: 'sentiment_satisfied' },
};

const URGENCY: Record<string, { label: string; tone: Tone }> = {
  critical: { label: 'Critical', tone: 'negative' },
  high: { label: 'High', tone: 'attention' },
  medium: { label: 'Medium', tone: 'neutral' },
  low: { label: 'Low', tone: 'neutral' },
};

export const INTENT_LABELS: Record<string, string> = {
  feature_request: 'Feature request',
  bug: 'Bug',
  usability: 'Usability',
  performance: 'Performance',
  integration: 'Integration',
  pricing: 'Pricing',
  compliance_security: 'Compliance & security',
  other: 'Other',
};

export const STATUS_OPTIONS: { value: TopicStatus; label: string; tone: Tone }[] = [
  { value: 'open', label: 'Open', tone: 'neutral' },
  { value: 'under_review', label: 'Under review', tone: 'info' },
  { value: 'planned', label: 'Planned', tone: 'progress' },
  { value: 'in_progress', label: 'In progress', tone: 'progress' },
  { value: 'shipped', label: 'Shipped', tone: 'positive' },
  { value: 'declined', label: 'Declined', tone: 'negative' },
];

const SPEAKER: Record<string, string> = { customer: 'Customer', agent: 'Agent', unknown: 'Unknown speaker' };

function Pill({ tone, icon, children, tip }: { tone: Tone; icon?: string; children: React.ReactNode; tip?: string }) {
  const palette = portal.signal[tone];
  const pill = (
    <Badge variant="soft" size="1" style={{ backgroundColor: palette.bg, color: palette.fg, gap: 4 }}>
      {icon ? <MaterialIcon name={icon} size={12} color={palette.fg} /> : null}
      {children}
    </Badge>
  );
  return tip ? <Tooltip content={tip}>{pill}</Tooltip> : pill;
}

export function StatusBadge({ status }: { status: TopicStatus | string | undefined }) {
  const option = STATUS_OPTIONS.find((o) => o.value === status) ?? STATUS_OPTIONS[0];
  return <Pill tone={option.tone}>{option.label}</Pill>;
}

export function UrgencyBadge({ urgency }: { urgency: string | undefined }) {
  const u = URGENCY[urgency ?? ''] ?? URGENCY.medium;
  return (
    <Pill tone={u.tone} icon="schedule" tip="Urgency">
      {u.label}
    </Pill>
  );
}

export function ToneBadge({ tone }: { tone: string | undefined }) {
  const t = TONE[tone ?? ''] ?? TONE.neutral;
  return (
    <Pill tone={t.tone} icon={t.icon} tip="Customer tone">
      {t.label}
    </Pill>
  );
}

export function ChurnRiskBadge() {
  return (
    <Pill tone="negative" icon="trending_down" tip="The customer signalled cancelling, not renewing or switching">
      Churn risk
    </Pill>
  );
}

/**
 * One line of chips summarising a piece of evidence. Neutral defaults
 * (medium urgency, neutral tone, plain feature request) are left out so the
 * signal that matters stands out.
 */
export function SignalChips({ evidence }: { evidence: Partial<EvidenceAttributes> }) {
  const showTone = evidence.tone && evidence.tone !== 'neutral';
  const showUrgency = evidence.urgency && evidence.urgency !== 'medium' && evidence.urgency !== 'low';
  const showIntent = evidence.intent && evidence.intent !== 'feature_request' && evidence.intent !== 'other';
  const showSpeaker = evidence.speaker_role && evidence.speaker_role !== 'customer';
  if (!showTone && !showUrgency && !showIntent && !showSpeaker && !evidence.churn_risk && !evidence.competitor && !evidence.product_area) {
    return null;
  }
  return (
    <Flex gap="1" wrap="wrap" align="center">
      {evidence.churn_risk ? <ChurnRiskBadge /> : null}
      {showUrgency ? <UrgencyBadge urgency={evidence.urgency} /> : null}
      {showTone ? <ToneBadge tone={evidence.tone} /> : null}
      {showIntent ? <Pill tone="info">{INTENT_LABELS[evidence.intent ?? ''] ?? evidence.intent}</Pill> : null}
      {evidence.competitor ? (
        <Pill tone="attention" icon="swap_horiz" tip="Competitor named">
          {evidence.competitor}
        </Pill>
      ) : null}
      {evidence.product_area ? <Pill tone="neutral">{evidence.product_area}</Pill> : null}
      {showSpeaker ? (
        <Pill tone="neutral" icon="support_agent" tip="Said by">
          {SPEAKER[evidence.speaker_role ?? ''] ?? evidence.speaker_role}
        </Pill>
      ) : null}
    </Flex>
  );
}

/** Business impact and workaround — the sentences a product leader quotes. */
export function ImpactLines({ evidence }: { evidence: Partial<EvidenceAttributes> }) {
  if (!evidence.business_impact && !evidence.workaround) return null;
  return (
    <Flex direction="column" gap="0">
      {evidence.business_impact ? (
        <Text size="1" style={{ color: portal.strong }}>
          <Text weight="medium">Impact:</Text> {evidence.business_impact}
        </Text>
      ) : null}
      {evidence.workaround ? (
        <Text size="1" style={{ color: portal.muted }}>
          <Text weight="medium">Workaround:</Text> {evidence.workaround}
        </Text>
      ) : null}
    </Flex>
  );
}
