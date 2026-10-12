"""Delete Customer Feature Intelligence evidence older than the retention window.

GDPR Art. 5(1)(e) / SOC 2 C1.2: evidence (verbatim excerpts) is kept only as
long as it is useful. Revenue history and customer identities are kept; topic
scores are recomputed from what remains. Every org's purge is written to the
intelligence audit log.

Env:
    INTELLIGENCE_RETENTION_DAYS   required (or pass --days)
    INTELLIGENCE_MYSQL_*          store connection (see backend/env.template)

Usage (idempotent; schedule daily via cron or a Kubernetes CronJob):
    python -m scripts.customer_intelligence.retention_purge [--days 365] [--org ORG_ID] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import timedelta

from app.models.intelligence import AuditEntry
from app.services.intelligence_store.intelligence_store_factory import IntelligenceStoreFactory
from app.services.intelligence_store.mysql.sql import utcnow

logger = logging.getLogger("intelligence.retention")


async def purge(days: int, org_ids: list[str] | None, *, dry_run: bool) -> int:
    store = await IntelligenceStoreFactory.create_store(logger)
    cutoff = utcnow() - timedelta(days=days)
    removed = 0
    try:
        for org_id in org_ids or await store.list_org_ids():
            if dry_run:
                logger.info("[dry-run] would purge evidence before %s for org %s", cutoff.date(), org_id)
                continue
            result = await store.purge_mentions_before(org_id, cutoff)
            removed += result.feature_gap_mentions + result.pain_point_mentions
            await store.record_audit(
                AuditEntry(
                    org_id=org_id,
                    actor="retention_purge",
                    action="retention.purge",
                    target_type="org",
                    target_id=org_id,
                    details={"cutoff": cutoff.isoformat(), "days": days, **result.model_dump()},
                )
            )
            logger.info("Org %s: purged %s", org_id, result.model_dump())
    finally:
        await store.close()
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=None, help="Retention window; defaults to INTELLIGENCE_RETENTION_DAYS")
    parser.add_argument("--org", action="append", dest="orgs", help="Limit to an org id (repeatable)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    raw = args.days if args.days is not None else os.getenv("INTELLIGENCE_RETENTION_DAYS", "").strip()
    if not raw:
        logger.info("INTELLIGENCE_RETENTION_DAYS is not set; nothing to purge")
        return 0
    days = int(raw)
    if days < 1:
        logger.error("Retention must be at least 1 day, got %s", days)
        return 2
    removed = asyncio.run(purge(days, args.orgs, dry_run=args.dry_run))
    logger.info("Done: %d mention(s) removed", removed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
