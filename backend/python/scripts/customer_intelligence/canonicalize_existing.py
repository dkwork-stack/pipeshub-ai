#!/usr/bin/env python3
"""Propose (and optionally apply) merges for near-duplicate intelligence topics/customers.

Default is dry-run. Pass ``--apply`` to call ``merge_topics`` / rename customers.

Usage:
    python -m scripts.customer_intelligence.canonicalize_existing --org ORG_ID
    python -m scripts.customer_intelligence.canonicalize_existing --org ORG_ID --apply
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from difflib import SequenceMatcher
from logging import getLogger

# Allow running as ``python scripts/customer_intelligence/canonicalize_existing.py``
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from app.modules.customer_intelligence.pipeline.stages import (  # noqa: E402
    normalize_customer_name,
    normalize_name,
)
from app.services.intelligence_store.intelligence_store_factory import (  # noqa: E402
    IntelligenceStoreFactory,
)

logger = getLogger("canonicalize_existing")
_TOPIC_SIM = float(os.getenv("INTELLIGENCE_TOPIC_SIMILARITY", "0.82"))
_CUST_SIM = float(os.getenv("INTELLIGENCE_CUSTOMER_SIMILARITY", "0.88"))


def _pairs(names: list[tuple[int | str, str]], threshold: float, normalize) -> list[tuple]:
    proposals = []
    for i, (id_a, name_a) in enumerate(names):
        for id_b, name_b in names[i + 1 :]:
            score = SequenceMatcher(None, normalize(name_a), normalize(name_b)).ratio()
            if score >= threshold:
                # Prefer keeping the shorter / earlier name as target
                source, target = (id_a, id_b) if len(name_a) > len(name_b) else (id_b, id_a)
                proposals.append((source, target, name_a, name_b, score))
    return proposals


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", required=True, help="org_id to canonicalize")
    parser.add_argument("--apply", action="store_true", help="Apply merges (default: dry-run)")
    args = parser.parse_args()

    store = await IntelligenceStoreFactory.create_store(logger)
    topics = await store.list_topics(args.org)
    by_kind: dict[str, list] = {}
    for t in topics:
        by_kind.setdefault(t.kind.value, []).append(t)

    print(f"Org {args.org}: {len(topics)} active topics")
    for kind, items in by_kind.items():
        proposals = _pairs(
            [(t.id, t.canonical_name) for t in items if t.id is not None],
            _TOPIC_SIM,
            normalize_name,
        )
        print(f"\n[{kind}] {len(proposals)} merge proposal(s):")
        for source, target, na, nb, score in proposals:
            print(f"  merge {source} ({na}) -> {target} ({nb}) score={score:.2f}")
            if args.apply:
                await store.merge_topics(args.org, int(source), int(target))
                print("    applied")

    customers = await store.list_customer_names(args.org)
    cust_proposals = _pairs(
        [(cid, name) for cid, name in customers],
        _CUST_SIM,
        normalize_customer_name,
    )
    print(f"\n[customers] {len(cust_proposals)} near-duplicate pair(s):")
    for source, target, na, nb, score in cust_proposals:
        print(f"  {source} ({na}) ~ {target} ({nb}) score={score:.2f}")
        if args.apply:
            # Prefer keeping target's id; rename is a soft suggestion — upsert
            # under target and leave source for manual review (no hard delete).
            print("    (customer merges require manual review; not auto-applied)")

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to merge topics.")
    await store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
