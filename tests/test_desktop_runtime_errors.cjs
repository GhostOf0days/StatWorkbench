const test = require('node:test');
const assert = require('node:assert/strict');
const {createRuntimeErrorTracker} = require('../scripts/desktop-runtime-errors.cjs');

test('desktop verification catches the Windows workbook-disposal exception across output chunks', () => {
  const tracker = createRuntimeErrorTracker();
  tracker.append('stdout', '[renderer:er');
  tracker.append('stderr', 'Chromium warning\n');
  tracker.append('stdout', "ror] Uncaught TypeError: Cannot destructure property 'rowData' of 'this._worksheetData' as it is null.\r\n");
  assert.equal(tracker.finish().length, 1);
});

test('desktop verification catches renderer crashes and load failures without a final newline', () => {
  const tracker = createRuntimeErrorTracker();
  tracker.append('stderr', '[desktop-smoke] renderer stopped { reason: crashed }\n[desktop-smoke] renderer failed to load: -6');
  assert.equal(tracker.finish().length, 2);
  assert.equal(tracker.finish().length, 2);
});

test('normal workflow and renderer warnings do not fail verification', () => {
  const tracker = createRuntimeErrorTracker();
  tracker.append('stdout', '[renderer:warning] Slow rendering\n[desktop-smoke] quit event: 0\n');
  assert.deepEqual(tracker.finish(), []);
});
