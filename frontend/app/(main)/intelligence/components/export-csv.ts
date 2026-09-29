export type CsvColumn<T> = {
  header: string;
  accessor: (row: T) => string | number | null | undefined;
};

/**
 * Exports the rows currently loaded on screen — there's no server-side
 * export endpoint, so this only covers the visible page, not the full
 * result set.
 */
export function exportRowsToCsv<T>(filename: string, columns: CsvColumn<T>[], rows: T[]): void {
  const escape = (value: string) => `"${value.replace(/"/g, '""')}"`;
  const header = columns.map((c) => escape(c.header)).join(',');
  const body = rows
    .map((row) => columns.map((c) => escape(String(c.accessor(row) ?? ''))).join(','))
    .join('\n');
  const csv = `${header}\n${body}`;

  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
