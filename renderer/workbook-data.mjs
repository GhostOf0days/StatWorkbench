// SPDX-License-Identifier: MIT
// Pure data validation shared by the workbook adapter and its tests.
export const WORKBOOK_LIMITS = Object.freeze({ rows: 100000, columns: 1000, cells: 2000000, sheets: 100, bytes: 64 * 1024 * 1024 });

export function columnLabel(index) {
  if (!Number.isInteger(index) || index < 0 || index >= WORKBOOK_LIMITS.columns) throw new Error('Column is out of range.');
  let text = '';
  for (let value = index + 1; value; value = Math.floor((value - 1) / 26)) text = String.fromCharCode(65 + (value - 1) % 26) + text;
  return text;
}

export function rangeA1(range) {
  const first = `${columnLabel(range.startColumn)}${range.startRow + 1}`;
  const last = `${columnLabel(range.endColumn)}${range.endRow + 1}`;
  return first === last ? first : `${first}:${last}`;
}

export function boundedRange(a1, { rows, columns, usedRows = rows, usedColumns = columns, sheetName } = {}) {
  if (typeof a1 !== 'string' || a1.length > 512) throw new Error('Enter a spreadsheet range such as A1:C20.');
  let text = a1.trim();
  const bang = text.lastIndexOf('!');
  if (bang !== -1) {
    const prefix = text.slice(0, bang).replace(/^'(.*)'$/, '$1').replace(/''/g, "'");
    if (prefix !== sheetName) throw new Error(`This range belongs to a different worksheet: ${prefix}.`);
    text = text.slice(bang + 1);
  }
  text = text.replace(/\$/g, '').toUpperCase();
  const col = (letters) => [...letters].reduce((n, c) => n * 26 + c.charCodeAt(0) - 64, 0) - 1;
  let match, range;
  if ((match = /^([A-Z]+)([1-9]\d*)(?::([A-Z]+)([1-9]\d*))?$/.exec(text))) {
    range = { startRow: Number(match[2]) - 1, endRow: Number(match[4] || match[2]) - 1, startColumn: col(match[1]), endColumn: col(match[3] || match[1]) };
  } else if ((match = /^([A-Z]+):([A-Z]+)$/.exec(text))) {
    range = { startRow: 0, endRow: Math.max(0, usedRows - 1), startColumn: col(match[1]), endColumn: col(match[2]) };
  } else if ((match = /^([1-9]\d*):([1-9]\d*)$/.exec(text))) {
    range = { startRow: Number(match[1]) - 1, endRow: Number(match[2]) - 1, startColumn: 0, endColumn: Math.max(0, usedColumns - 1) };
  } else throw new Error('Enter one rectangular range, such as A1:C20, A:C, or 1:3.');
  if (range.startRow > range.endRow || range.startColumn > range.endColumn) throw new Error('The range end must follow its start.');
  if (range.endRow >= Math.min(rows, WORKBOOK_LIMITS.rows) || range.endColumn >= Math.min(columns, WORKBOOK_LIMITS.columns)) throw new Error('The range exceeds the worksheet bounds.');
  if ((range.endRow - range.startRow + 1) * (range.endColumn - range.startColumn + 1) > WORKBOOK_LIMITS.cells) throw new Error('Select at most 2,000,000 cells for analysis.');
  return range;
}

export function matrixToCells(matrix) {
  if (!Array.isArray(matrix)) throw new Error('Worksheet data must be a matrix.');
  const columns = matrix.reduce((max, row) => {
    if (!Array.isArray(row)) throw new Error('Each worksheet row must be an array.');
    return Math.max(max, row.length);
  }, 0);
  if (matrix.length > WORKBOOK_LIMITS.rows || columns > WORKBOOK_LIMITS.columns || matrix.length * columns > WORKBOOK_LIMITS.cells) throw new Error('Worksheet data exceeds the row, column, or cell limit.');
  const cellData = {};
  let textLength = 0;
  matrix.forEach((row, r) => row.forEach((value, c) => {
    if (value === null || value === undefined) return;
    if (!['string', 'number', 'boolean'].includes(typeof value) || (typeof value === 'number' && !Number.isFinite(value))) throw new Error('Cells must contain finite numbers, text, booleans, or null.');
    if (typeof value === 'string') {
      textLength += value.length;
      if (value.length > 1000000 || textLength > 16000000) throw new Error('Worksheet text exceeds the size limit.');
    }
    // Explicit types preserve leading zeros and keep imported formulas inert.
    const t = typeof value === 'string' ? 1 : typeof value === 'number' ? 2 : 3;
    (cellData[r] ||= {})[c] = { v: value, t };
  }));
  return { cellData, rows: matrix.length, columns };
}

export function uniqueSheetName(value, existing) {
  const base = String(value || 'Sheet').replace(/[\\/?*\[\]:]/g, ' ').trim().slice(0, 31) || 'Sheet';
  const names = new Set(existing.map((name) => name.toLocaleLowerCase()));
  let candidate = base, suffix = 2;
  while (names.has(candidate.toLocaleLowerCase())) {
    const tail = ` (${suffix++})`;
    candidate = base.slice(0, 31 - tail.length) + tail;
  }
  return candidate;
}

export function validateSnapshot(snapshot) {
  if (!snapshot || typeof snapshot !== 'object' || Array.isArray(snapshot)) throw new Error('The project does not contain a workbook.');
  const serialized = JSON.stringify(snapshot);
  if (new TextEncoder().encode(serialized).length > WORKBOOK_LIMITS.bytes) throw new Error('Workbook snapshot exceeds 64 MiB.');
  const copy = JSON.parse(serialized);
  if (!Array.isArray(copy.sheetOrder) || !copy.sheetOrder.length || copy.sheetOrder.length > WORKBOOK_LIMITS.sheets || new Set(copy.sheetOrder).size !== copy.sheetOrder.length || !copy.sheets || typeof copy.sheets !== 'object') throw new Error('Invalid workbook sheet list.');
  let count = 0;
  for (const id of copy.sheetOrder) {
    if (typeof id !== 'string' || !Object.hasOwn(copy.sheets, id)) throw new Error('A workbook sheet is missing.');
    const sheet = copy.sheets[id];
    if (!sheet || typeof sheet !== 'object') throw new Error('Invalid worksheet.');
    const rows = sheet.rowCount ?? 1000, columns = sheet.columnCount ?? 26;
    if (!Number.isInteger(rows) || rows < 1 || rows > WORKBOOK_LIMITS.rows || !Number.isInteger(columns) || columns < 1 || columns > WORKBOOK_LIMITS.columns) throw new Error('A worksheet exceeds the supported dimensions.');
    for (const [row, cells] of Object.entries(sheet.cellData || {})) {
      if (!/^\d+$/.test(row) || Number(row) >= rows || !cells || typeof cells !== 'object') throw new Error('Invalid worksheet row.');
      for (const [column, cell] of Object.entries(cells)) {
        if (!/^\d+$/.test(column) || Number(column) >= columns || (cell !== null && (typeof cell !== 'object' || Array.isArray(cell)))) throw new Error('Invalid worksheet cell.');
        if (++count > WORKBOOK_LIMITS.cells) throw new Error('Workbook has more than 2,000,000 stored cells.');
      }
    }
  }
  return copy;
}
