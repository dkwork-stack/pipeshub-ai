'use client';

import { useMemo, useState } from 'react';

export type SortDirection = 'asc' | 'desc';

/**
 * Sorts the currently-loaded page of rows client-side. The API has no
 * `sort_by` param, so this only orders what's already on screen — it does
 * not re-fetch or sort across pages.
 */
export function useClientSort<T, K extends string>(
  items: T[] | undefined,
  getValue: (row: T, key: K) => string | number | null | undefined,
  defaultKey: K,
  defaultDir: SortDirection = 'desc',
) {
  const [sortKey, setSortKey] = useState<K>(defaultKey);
  const [sortDir, setSortDir] = useState<SortDirection>(defaultDir);

  const sorted = useMemo(() => {
    if (!items) return items;
    const copy = [...items];
    copy.sort((a, b) => {
      const av = getValue(a, sortKey);
      const bv = getValue(b, sortKey);
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      const cmp = typeof av === 'number' && typeof bv === 'number' ? av - bv : String(av).localeCompare(String(bv));
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return copy;
  }, [items, sortKey, sortDir, getValue]);

  const toggleSort = (key: K) => {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  return { sorted, sortKey, sortDir, toggleSort };
}
