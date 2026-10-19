// SPDX-License-Identifier: MIT
const test = require('node:test');
const assert = require('node:assert/strict');
const helpers = import('../renderer/workbook-data.mjs');

test('A1 references preserve offsets, absolute references and quoted sheet names', async () => {
  const { boundedRange, rangeA1 } = await helpers;
  const range = boundedRange("'Study 1'!$B$3:$D$7", { rows: 1000, columns: 26, sheetName: 'Study 1' });
  assert.deepEqual(range, { startRow: 2, endRow: 6, startColumn: 1, endColumn: 3 });
  assert.equal(rangeA1(range), 'B3:D7');
});
test('whole columns and rows are clipped to occupied dimensions', async () => {
  const { boundedRange } = await helpers;
  const size = { rows: 1000, columns: 26, usedRows: 12, usedColumns: 6 };
  assert.equal(boundedRange('B:D', size).endRow, 11);
  assert.equal(boundedRange('2:5', size).endColumn, 5);
});
test('range validation rejects ambiguity, inversions, out-of-bounds and huge rectangles', async () => {
  const { boundedRange } = await helpers;
  const size = { rows: 100000, columns: 1000, sheetName: 'Data' };
  for (const text of ['A0', 'A1,B2', 'B2:A1', 'Sheet2!A1', 'A100001', 'ZZZ1', 'A1:ALL100000']) assert.throws(() => boundedRange(text, size));
});
test('matrix import preserves numeric identifiers, text that resembles formulas, blanks and booleans', async () => {
  const { matrixToCells } = await helpers;
  const { cellData, rows, columns } = matrixToCells([['00123', '=1+1', null, '', false], [0]]);
  assert.equal(rows, 2); assert.equal(columns, 5);
  assert.deepEqual(cellData[0][0], { v: '00123', t: 1 });
  assert.deepEqual(cellData[0][1], { v: '=1+1', t: 1 });
  assert.equal(cellData[0][2], undefined);
  assert.deepEqual(cellData[0][3], { v: '', t: 1 });
  assert.deepEqual(cellData[0][4], { v: false, t: 3 });
  assert.deepEqual(cellData[1][0], { v: 0, t: 2 });
});
test('matrix import rejects objects and nonfinite numbers', async () => {
  const { matrixToCells } = await helpers;
  for (const value of [NaN, Infinity, {}, []]) assert.throws(() => matrixToCells([[value]]));
});
test('sheet names are sanitized, bounded and unique case-insensitively', async () => {
  const { uniqueSheetName } = await helpers;
  assert.equal(uniqueSheetName('Results', ['results']), 'Results (2)');
  assert.equal(uniqueSheetName('Data/Copy', []), 'Data Copy');
  assert.ok(uniqueSheetName('A'.repeat(40), ['A'.repeat(31)]).length <= 31);
});
test('snapshot validation retains formulas, styles and resources without mutating original', async () => {
  const { validateSnapshot } = await helpers;
  const original = { id: 'w', sheetOrder: ['s'], sheets: { s: { rowCount: 10, columnCount: 5, cellData: { 0: { 0: { f: '=2+3', s: 'bold' } } } } }, styles: { bold: { bl: 1 } }, resources: [] };
  const copy = validateSnapshot(original);
  assert.deepEqual(copy, original);
  copy.sheets.s.cellData[0][0].f = '=4';
  assert.equal(original.sheets.s.cellData[0][0].f, '=2+3');
});
test('snapshot validation rejects duplicate/missing sheets and out-of-bounds stored cells', async () => {
  const { validateSnapshot } = await helpers;
  assert.throws(() => validateSnapshot({ sheetOrder: ['s', 's'], sheets: { s: {} } }));
  assert.throws(() => validateSnapshot({ sheetOrder: ['s'], sheets: {} }));
  assert.throws(() => validateSnapshot({ sheetOrder: ['s'], sheets: { s: { rowCount: 2, columnCount: 2, cellData: { 9: { 0: { v: 1 } } } } } }));
});
