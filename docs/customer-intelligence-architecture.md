# Customer Feature Intelligence — Architecture

Status: Phase 1 implemented on `feature/test1`. Phases 2–3 are the roadmap.
Supersedes the data-flow part of `docs/indexing-service.md` §8; that section
still describes the store and the original intake API.

## 1. What the product does

For every customer touchpoint — an uploaded CSV/Excel row or document, a
support ticket with its back-and-forth replies, a CRM case, a call transcript —
infer the **pain points** the customer describes and the **feature gaps**
(asks) they raise. Classify each one against every ask already known for the
org (from this sync or any earlier one). Identical asks collapse onto one
**topic** whose count, evidence, customer tone and citation links accumulate.
Revenue (ARR/MRR, parsed from uploads today, from billing connectors later)
weights each topic so product leaders see *what to build next and how much
revenue is behind it*.

Target buyers are mid-market and enterprise, so the design assumes SOC 2 Type II
and GDPR from the start: tenant isolation, PII minimisation, erasure, audit,
retention and provenance are first-class, not retrofits.

## 2. Design principles

1. **One contract in, many sources.** Every source — upload, connector, script,
   partner API — produces the same versioned `SignalEnvelope`. Nothing
   downstream knows which source it came from.
2. **Indexing never waits on intelligence.** The indexing service only
   normalises a record (cheap, deterministic) and publishes envelopes. LLM
   work happens in a separate, independently scalable worker.
3. **Everything behind an interface.** Store (`IIntelligenceStore` /
   `IIntelligenceQueryRepository`), dispatch (`ISignalDispatcher`), topic
   matching (`ITopicMatcher`), embeddings (`ITextEmbedder`), PII redaction
   (`IPiiRedactor`) and source normalisation (`SignalNormalizer` registry) are
   all swappable without touching the pipeline.
4. **Evidence or it didn't happen.** Every stored ask carries a verbatim quote
   that is verified to exist in the source, a link back to it, who said it and
   which model/prompt version produced it.
5. **Read and write are separate processes.** Portal reads never compete with
   ingestion; each scales on its own.

## 3. Components

```
 Sources                              Normalise + publish (cheap)            Analyse (LLM, scalable)                  Serve
 ─────────────────────────────        ─────────────────────────────         ──────────────────────────────           ───────────────────────
 KB upload (CSV/XLSX/PDF/DOCX) ─┐
 Zammad / ServiceNow tickets ───┤     Indexing service (:8091)
 Salesforce cases ──────────────┼──►  SinkOrchestrator                       Intelligence worker (:8095)
 Zoom / meeting transcripts ────┤       └ IntelligenceSourcePolicy  ──┐       app.intelligence_worker_main
 Future connectors ─────────────┘       └ SignalNormalizer registry   │        consumes `intelligence-events`
                                         (rows / thread / transcript │        (key = org_id)
 Sync scripts (Freshdesk, SF,           / document)                   │          │
 Chargebee) and partner APIs ───────►  POST /api/v1/intelligence/*   ├─► ISignalDispatcher ──► broker ──►  CustomerIntelligenceIngestionService
                                         (intake, org-scoped)         │   (broker | inline)                 1 PII redaction  (IPiiRedactor)
                                                                      │                                      2 LLM extraction (Extraction svc :8093)
                                                                      │                                      3 Verify quotes → dedupe
                                                                      │                                      4 Classify vs known topics
                                                                      │                                        (ITopicMatcher: lexical + embeddings)
                                                                      │                                      5 Resolve customer
                                                                      │                                      6 Persist mentions + provenance
                                                                      │                                      7 Recompute topic aggregates
                                                                      │                                              │
                                                                      │                                              ▼
                                                                      │                                     MySQL intelligence store
                                                                      │                                     (IIntelligenceStore)
                                                                      │                                              │
                                                                      │                      Portal API (:8094) ◄────┘  IIntelligenceQueryRepository
                                                                      │                      app.intelligence_main
                                                                      │                              ▲
                                                                      │                      Node gateway /api/v1/intelligence-portal/*
                                                                      │                      (JWT/PAT/OAuth, scopes intelligence:read|write)
                                                                      │                              ▲
                                                                      └──────────────────── Frontend /intelligence dashboards
```

| Component | Process | Scales by | Owns |
| --- | --- | --- | --- |
| Normalisers + source policy | indexing (:8091) | indexing replicas | turning a `Record` into envelopes |
| Intake API | indexing (:8091) | indexing replicas | external sources posting envelopes |
| Dispatcher | wherever envelopes are produced | — | broker vs inline delivery |
| Intelligence worker | `app.intelligence_worker_main` (:8095) | worker replicas × `INTELLIGENCE_WORKER_CONCURRENCY` | the analysis pipeline |
| Extraction | `app.extraction_main` (:8093) | extraction replicas | LLM prompt + structured output |
| Portal API | `app.intelligence_main` (:8094) | portal replicas | read models, topic curation, erasure |
| Store | MySQL (`INTELLIGENCE_MYSQL_*`) | read replicas / partitioning (Phase 3) | all intelligence data |

## 4. Contracts

### 4.1 `SignalEnvelope` (v1) — the only thing that crosses the broker

Defined in `app/modules/customer_intelligence/signals/envelope.py`; published
as `{"eventType": "intelligence.signal", "payload": <envelope>}`.

```jsonc
{
  "schema_version": 1,
  "org_id": "org_123",
  "source_connector": "zammad",            // file_upload, salesforce, zoom, ...
  "source_type": "support_ticket",         // support_ticket | crm_note | call_transcript | email | chat | document_upload
  "external_event_id": "rec_abc",          // idempotency key; table rows use "rec_abc:row:17"
  "source_record_id": "rec_abc",           // PipesHub record id — lineage and erasure key
  "occurred_at": "2026-10-01T09:30:00",
  "citation_url": "https://helpdesk/…/42",
  "turns": [                                // conversation-aware; one turn for a document or row
    { "role": "customer", "author": "Jane Roe", "text": "We need SSO before rollout…" },
    { "role": "agent",    "author": "Sam",      "text": "SSO is not available today." }
  ],
  "customer_external_id": null,            // known customer; null -> inferred by the extractor
  "customer_name": null,
  "customer_name_fallback": "Acme Corp",   // reporter's email domain / upload file name
  "cells": null,                           // tabular row cells; ARR/MRR parsed only for revenue sources
  "metadata": { "record_name": "Login issues", "record_type": "TICKET" }
}
```

* The envelope is self-contained: the worker needs no graph, vector or blob
  access, only the broker, the extraction service and the store. That keeps
  the worker small and its blast radius narrow.
* Large inputs are split *before* publishing (one envelope per table row,
  turn text capped at `INTELLIGENCE_MAX_TURN_CHARS`, threads capped at 40
  turns keeping the opening ask and the latest replies), so messages stay small.
* Revenue is never a field a source can set: the worker parses ARR/MRR from
  `cells` only when `source_connector` is an allowlisted revenue source
  (`file_upload`, `chargebee`).
* Partition key is `org_id`. On Kafka one org's envelopes are handled by one
  consumer at a time, which makes topic creation race-free without
  distributed locks; throughput across orgs scales with partitions and
  workers. On Redis Streams several consumers may hold one org's envelopes;
  the per-org lock is per process, so two workers can occasionally create
  near-duplicate topics. The unique key stops exact duplicates, and PMs (or
  the Phase 2 consolidation job) merge the rest.

### 4.2 Conversation turns

Tickets arrive from connectors as a description block group plus one
`COMMENT` block group per reply. `ThreadNormalizer` turns them into ordered
turns and labels each as `customer`, `agent` or `unknown` (matching the
ticket's reporter/creator name or email against the reply author). The prompt
renders turns as `[Customer · Jane]: …` and is told to **attribute asks to
customer turns only**; agent turns are context ("that isn't supported
today" corroborates a gap rather than creating one). With PII redaction on,
author names are dropped before the LLM call and only role labels remain.
Meeting transcripts are split on `Speaker: text` lines (`TranscriptNormalizer`).

When a source carries no customer id, attribution falls back in order:
known customer matched by name → the row's customer/account column → the
customer the LLM read from the text → the reporter's company email domain or
the upload's file name → `Unattributed`.

## 5. Analysis pipeline (worker)

1. **Redact** — `IPiiRedactor` masks emails, phone numbers, card numbers,
   national IDs and IBANs before any text leaves for the LLM. Default
   `RegexPiiRedactor`; a Presidio/DLP adapter can replace it. Customer
   (company) names are business data and are kept.
2. **Extract** — one LLM call per envelope through the extraction service.
   Output per item: name, description, verbatim excerpt, confidence, sentiment,
   tone, urgency, intent, product area, business impact, workaround,
   competitor, churn-risk flag, speaker role.
3. **Verify** — drop any item whose excerpt is not in the (redacted) source text.
4. **Dedupe** within the envelope.
5. **Classify against known topics** (`ITopicMatcher`, details in §6).
6. **Resolve customer** — exact then fuzzy match against known customers;
   corporate suffixes ignored.
7. **Persist** — idempotent upserts keyed on
   `(org, customer, topic, external_event_id)`; each mention records
   `source_record_id`, `extraction_model` and `prompt_version`.
8. **Aggregate** — recompute only the touched topics with set-based queries.

Failure isolation: an envelope that fails is retried by the broker consumer
(`RetryManager`), then dead-lettered; it never blocks the next envelope, and it
never blocks indexing.

## 6. Classifying an ask against past asks

The question "is this the same ask we already have?" is answered in three
tiers, cheapest first:

| Tier | How | Decision |
| --- | --- | --- |
| 1. Hint | The prompt carries the org's most relevant existing topics; the LLM may return `topic_id` | accepted if the id exists |
| 2. Lexical | normalised exact name / alias, then `SequenceMatcher` ≥ `INTELLIGENCE_TOPIC_SIMILARITY` (0.82) | attach |
| 3. Semantic | cosine similarity of embeddings (name + description) vs every topic of the same kind ≥ `INTELLIGENCE_TOPIC_EMBED_SIMILARITY` (0.86) | attach |
| — | nothing matched | create a new topic |

* Embeddings use the org's configured embedding model (same one the platform
  uses for search). Topic vectors are cached in `intelligence_topic_embeddings`
  keyed by `(topic_id, model)`; switching models re-embeds lazily.
* If no embedding model is configured, tier 3 is skipped and the system still
  works on tiers 1–2.
* Matched topics keep the new phrasing as an alias, so lexical matching gets
  better over time and the prompt hint list stays accurate.
* Humans stay in charge: the portal lets PMs rename, add guidance
  (`exclude: …`), merge two topics, and set a lifecycle status. Merges rewrite
  history and are audited.
* Phase 2 adds a periodic consolidation job that clusters topics created close
  together and proposes merges for review.

## 7. What is stored (and why)

### 7.1 Per mention (one piece of evidence)

| Field | Why it matters |
| --- | --- |
| verbatim `excerpt`, `citation_url`, `source_record_id` | proof, deep link, erasure/lineage key |
| `speaker_role` | an agent saying "we don't support X" ≠ a customer asking for X |
| `sentiment` (Positive/Neutral/Negative) | aggregate mood per topic and customer |
| `tone` (frustrated, angry, anxious, neutral, appreciative) | escalation triage; the "customer tone" the brief asks for |
| `urgency` (low → critical) | "blocking go-live" vs "nice to have" |
| `intent` (feature request, bug, usability, performance, integration, pricing, compliance/security, other) | routes asks to the right team; separates bugs from gaps |
| `product_area` | roll-ups by area/owner |
| `business_impact` | "blocking a 300-seat rollout" — the sentence a CPO quotes |
| `workaround` | how painful the gap really is |
| `competitor` | competitive pressure per gap |
| `churn_risk` | flags renewal risk tied to a specific ask |
| `confidence`, `extraction_model`, `prompt_version` | trust filtering, reproducibility, model audits |

### 7.2 Per topic (aggregated)

Customer count, mention count, ARR/MRR at stake, score, top customers,
`first_seen_at`, `last_seen_at`, mentions in the last 30 days vs the 30 before
(trend), share of negative sentiment, high-urgency count, churn-risk count,
competitors named, lifecycle `status` (open → under review → planned → in
progress → shipped → declined).

### 7.3 Per customer

Latest revenue, open asks, pain points, negative-tone share, churn-risk
mentions, last touchpoint, renewal date (when a billing source provides it).

### 7.4 Worth adding next (Phase 2–3)

* **Roadmap link** — tie a topic to a Jira/Linear issue (both connectors exist)
  so status syncs automatically, and when it ships, produce the
  "close the loop" list: every customer and contact who asked.
* **Segments** — plan tier, industry, region and lifecycle stage from CRM, to
  answer "what do enterprise customers in EMEA ask for?".
* **Renewal-weighted ARR** — ARR renewing in the next 90 days that is attached
  to an ask; better urgency signal than total ARR.
* **Deal-blocker ARR** — pipeline (open opportunity) value blocked by a gap,
  from CRM deals.
* **Persona** — job title/role of the asker (admin, end user, exec sponsor).
* **Weekly digest** — new and fast-rising asks per product area, by email/Slack.
* **Agent tools** — expose the read API as tools to PipesHub's in-product
  agents ("which customers asked for audit logs this quarter?").

## 8. Data model (MySQL)

All tables carry `org_id`; every query filters on it.

| Table | Purpose |
| --- | --- |
| `customers` | identity per org (`external_customer_id`, name) |
| `revenue_snapshots` | append-only ARR/MRR history |
| `intelligence_topics` | canonical asks/pain points per org: aliases, guidance, status, first/last seen, merge pointer |
| `intelligence_topic_embeddings` | cached vectors per topic and model |
| `feature_gap_mentions` / `pain_point_mentions` | evidence rows (fields in §7.1) |
| `feature_gaps` / `feature_gap_scores` | topic roll-ups and score (§7.2) |
| `intelligence_audit_log` | who did what: topic edits, merges, erasures, retention purges |

Schema evolution: `create_all` creates missing tables, and an additive
migrator adds missing **nullable** columns on start-up. Destructive changes
need an explicit migration (Phase 3: Alembic).

## 9. Security and compliance controls

| Control | Implementation | Maps to |
| --- | --- | --- |
| Tenant isolation | `org_id` on every row and query; org always taken from the authenticated token, a mismatching client `org_id` is rejected (403) | SOC 2 CC6.1; GDPR Art. 32 |
| Least privilege | `intelligence:read` for dashboards, `intelligence:write` for curation and erasure, enforced at the Node gateway | SOC 2 CC6.3 |
| Data minimisation | PII redaction before the LLM and before storing excerpts; only the excerpt is stored, never the full ticket | GDPR Art. 5(1)(c), Art. 25 |
| Right to erasure | `DELETE /customers/{id}` removes the customer, its mentions and revenue and recomputes aggregates; `erase_source_record` removes everything derived from one record | GDPR Art. 17 |
| Retention | `scripts/customer_intelligence/retention_purge.py` deletes evidence older than `INTELLIGENCE_RETENTION_DAYS` (default off) | GDPR Art. 5(1)(e); SOC 2 C1.2 |
| Audit trail | `intelligence_audit_log` for topic edits, merges, erasures, purges (actor, action, target, time) | SOC 2 CC7.2, CC8.1; GDPR Art. 30 |
| Provenance | `extraction_model`, `prompt_version`, `source_record_id` on every mention | SOC 2 PI1.x; EU AI Act transparency |
| Encryption in transit | broker and MySQL TLS (`INTELLIGENCE_MYSQL_SSL`, broker SSL config) | SOC 2 CC6.7 |
| Encryption at rest | managed MySQL / volume encryption (deployment) | SOC 2 CC6.1 |
| Processing opt-in | `IntelligenceSourcePolicy` (which record types/connectors feed the pipeline); per-org consent flag in Phase 2 | GDPR Art. 6 |
| Sub-processors | the LLM provider is the org's configured provider (it can be self-hosted); record it in the sub-processor list | GDPR Art. 28 |

## 10. Scalability

* **Indexing cost:** normalising a record and publishing envelopes is O(record
  size) with no network calls other than the broker; LLM latency is fully off
  the indexing path.
* **Worker throughput:** ≈ `workers × INTELLIGENCE_WORKER_CONCURRENCY ÷ LLM
  latency`. Partitioning by `org_id` keeps orgs fair and topic creation
  race-free; within one worker, extraction for different envelopes of the same
  org runs concurrently and only the short classify-and-write step is
  serialised per org.
* **Cost controls:** keyword pre-screen skips envelopes with no signal;
  `INTELLIGENCE_UPLOAD_MAX_ROWS` caps rows per upload; topic embeddings are
  cached; prompt hints are capped per kind.
* **Aggregates:** recomputed only for touched topics with set-based SQL (no
  per-customer round trips).
* **Read path:** separate process; queries are paged, use window functions for
  latest revenue and composite indexes on `(org_id, topic)`; read replicas
  behind `IIntelligenceQueryRepository` when needed.
* **Phase 3:** move topic vectors to the platform vector DB
  (`IVectorDBService`) once an org exceeds ~50k topics; partition mention tables
  by `org_id`; materialise daily trend buckets.

## 11. Dashboards

Built on the existing Cooper portal shell (`frontend/app/(main)/intelligence`):
shared filters (search, source, plus page-specific ones), sortable columns
and CSV export on every list. Every number on screen comes from an API field;
nothing is interpolated.

* **Overview** — KPIs (ARR/MRR at stake, feature gaps, pain points,
  customers, mentions); top customers by ARR; top asks by score; *Emerging
  asks* (last 30 days vs the 30 before); *At-risk customers* (churn signals
  or mostly negative evidence, by ARR); *Voice of the customer* (ask-type and
  sentiment mix).
* **Feature gaps** — filters for status and ask type; columns for ARR/MRR at
  stake, customers, mentions, score, 30-day trend, top urgency, status, top
  customers. Detail: status control, *How customers talk about it* (activity,
  urgency and tone mix, churn signals, negative share, competitors), extraction
  guidance and merge, affected customers, and evidence with quote, impact,
  workaround and signal chips (churn risk, urgency, tone, ask type,
  competitor, product area, speaker).
* **Pain points** — status filter; 30-day trend, negative share and status
  columns. Detail mirrors feature gaps.
* **Customers** — All / At-risk toggle (linked from the overview); health
  column (churn signals, negative share, competitors), pain points, last
  touch. Detail: revenue, *Account health*, requested features, pain points,
  evidence, and an *Erase customer data* action (typed confirmation,
  `intelligence:write`, audited).

Later: linking pain points to the feature gaps that would resolve them, a
recent-evidence feed, and an audit-log view for admins (the API exists:
`GET /intelligence-portal/audit`).

## 12. Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `INTELLIGENCE_DISPATCH_MODE` | `inline` (code), `broker` (compose/helm) | how envelopes reach the pipeline |
| `INTELLIGENCE_SOURCE_RECORD_TYPES` | `TICKET,CASE,MEETING` | connector record types analysed (KB uploads are always analysed) |
| `INTELLIGENCE_SOURCE_CONNECTORS` | empty (all) | optional connector allowlist |
| `INTELLIGENCE_WORKER_CONCURRENCY` | `8` | envelopes analysed in parallel per worker |
| `INTELLIGENCE_WORKER_PORT` | `8095` | worker health port |
| `INTELLIGENCE_PII_REDACTION` | `true` | redact PII before LLM/storage |
| `INTELLIGENCE_TOPIC_EMBED_SIMILARITY` | `0.86` | semantic match threshold |
| `INTELLIGENCE_TOPIC_SIMILARITY` | `0.82` | lexical match threshold |
| `INTELLIGENCE_RETENTION_DAYS` | unset | evidence retention for the purge script |
| `INTELLIGENCE_MAX_TURN_CHARS` | `4000` | per-turn cap before publishing |

## 13. Phases

* **Phase 1 (this change):** envelope + normalisers (rows, documents, ticket
  threads, transcripts); broker dispatch + worker; conversation-aware
  extraction with tone/urgency/intent/impact/workaround/competitor/churn;
  semantic topic matching; provenance; PII redaction; erasure, retention and
  audit; set-based aggregates with trend; dashboard upgrades.
* **Phase 2:** per-org consent and source settings in the UI, consolidation
  job, roadmap links and close-the-loop, segments, renewal- and
  deal-weighted ARR, weekly digest, agent tools.
* **Phase 3:** Alembic migrations, vector DB for topics at very large scale,
  partitioned tables, data-residency routing per org.
