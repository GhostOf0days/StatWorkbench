// SPDX-License-Identifier: MIT
// Workbook adapter for the built-in spreadsheet engine.
import { createUniver, LocaleType, mergeLocales, CommandType, LifecycleStages, greenTheme } from '@univerjs/presets';
import { UniverSheetsCorePreset } from '@univerjs/preset-sheets-core';
import UniverPresetSheetsCoreEnUS from '@univerjs/preset-sheets-core/locales/en-US';
import { UniverSheetsDrawingPreset } from '@univerjs/preset-sheets-drawing';
import UniverPresetSheetsDrawingEnUS from '@univerjs/preset-sheets-drawing/locales/en-US';
import { UniverSheetsSortPreset } from '@univerjs/preset-sheets-sort';
import UniverPresetSheetsSortEnUS from '@univerjs/preset-sheets-sort/locales/en-US';
import '@univerjs/preset-sheets-core/lib/index.css';
import '@univerjs/preset-sheets-drawing/lib/index.css';
import '@univerjs/preset-sheets-sort/lib/index.css';
import { WORKBOOK_LIMITS, boundedRange, matrixToCells, rangeA1, uniqueSheetName, validateSnapshot } from './workbook-data.mjs';
import { renderChart } from './charts.js';
import { WorkbookChartRegistry, WorkbookImageRegistry } from './workbook-charts.mjs';
import { registerLegacyFunctions } from './legacy-functions.mjs';
import { FormulaDataModel } from '@univerjs/engine-formula';

function id(prefix) { return `${prefix}-${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`}`; }
function clone(value) { return JSON.parse(JSON.stringify(value)); }

const IMAGE_BYTES = 16 * 1024 * 1024;
async function pictureDisplaySource(source, { width, height }, native) {
  if (typeof source !== 'string' || source.length > Math.ceil(IMAGE_BYTES / 3) * 4 + 100 || !/^data:image\/(?:png|jpeg|gif|webp|bmp);base64,[A-Za-z0-9+/]+={0,2}$/i.test(source)) throw new Error('Pictures must contain an embedded PNG, JPEG, GIF, WebP, or BMP image of at most 16 MiB.');
  const mode = native.pictureStretch ?? 0, border = native.borderStyle ?? 'none';
  if (![0, 1, 2, 3].includes(mode)) throw new Error('The picture uses an unknown layout mode.');
  if (!['none', 'solid', 'dashed', 'dotted', 'double'].includes(border)) throw new Error(`The picture border style ${border} is not supported.`);
  if (native.fixedPosition === true) throw new Error('Fixed-viewport pictures cannot be restored as worksheet drawings.');
  if (mode === 0 && border === 'none' && !native.backColor && native.isVisible !== false) return source;
  const bitmap = new Image();
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => { bitmap.src = ''; reject(new Error('Picture decoding timed out.')); }, 10000);
    bitmap.onload = () => { clearTimeout(timer); resolve(); };
    bitmap.onerror = () => { clearTimeout(timer); reject(new Error('The embedded picture could not be decoded.')); };
    bitmap.src = source;
  });
  const canvas = document.createElement('canvas');
  canvas.width = Math.ceil(width); canvas.height = Math.ceil(height);
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Picture rendering is unavailable.');
  const color = value => typeof value === 'string' && CSS.supports('color', value) ? value : null;
  if (native.isVisible !== false) {
    if (color(native.backColor)) { context.fillStyle = color(native.backColor); context.fillRect(0, 0, width, height); }
    let imageWidth = width, imageHeight = height, x = 0, y = 0;
    if (mode === 1 || mode === 3) {
      imageWidth = bitmap.naturalWidth; imageHeight = bitmap.naturalHeight;
      if (mode === 1) { x = Math.max(0, (width - imageWidth) / 2); y = Math.max(0, (height - imageHeight) / 2); }
    } else if (mode === 2) {
      const scale = Math.min(width / bitmap.naturalWidth, height / bitmap.naturalHeight);
      imageWidth = bitmap.naturalWidth * scale; imageHeight = bitmap.naturalHeight * scale;
      x = (width - imageWidth) / 2; y = (height - imageHeight) / 2;
    }
    context.drawImage(bitmap, x, y, imageWidth, imageHeight);
    if (border !== 'none') {
      const thickness = Math.max(0, Math.min(100, Number(native.borderWidth ?? 1)));
      if (!Number.isFinite(thickness)) throw new Error('Invalid picture border width.');
      context.strokeStyle = color(native.borderColor) || '#000000'; context.lineWidth = thickness;
      if (border === 'dashed') context.setLineDash([thickness * 3, thickness * 2]);
      if (border === 'dotted') context.setLineDash([thickness, thickness]);
      const radius = Math.max(0, Math.min(Number(native.borderRadius) || 0, width / 2, height / 2));
      const outline = inset => { context.beginPath(); context.roundRect(inset, inset, Math.max(0, width - 2 * inset), Math.max(0, height - 2 * inset), radius); context.stroke(); };
      if (border === 'double') { context.lineWidth = thickness / 3; outline(thickness / 6); outline(thickness * 5 / 6); }
      else outline(thickness / 2);
    }
  }
  const rendered = canvas.toDataURL('image/png');
  if (rendered.length > Math.ceil(IMAGE_BYTES / 3) * 4 + 100) throw new Error('The displayed picture exceeds 16 MiB.');
  return rendered;
}

export function chartImageSource(chart) {
  const wrapper = document.createElement('div');
  wrapper.innerHTML = renderChart(chart);
  const plot = wrapper.querySelector('svg');
  if (!plot) throw new Error(wrapper.textContent || 'This chart cannot be rendered.');
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  const legend = [...wrapper.querySelectorAll('.legend span')].map((entry) => ({ text: entry.textContent, color: entry.querySelector('i')?.style.background || '#4869df' }));
  const height = 330 + Math.ceil(legend.length / 3) * 18;
  svg.setAttribute('xmlns', ns); svg.setAttribute('viewBox', `0 0 680 ${height}`);
  svg.setAttribute('width', '680'); svg.setAttribute('height', String(height));
  svg.setAttribute('font-family', 'Arial, sans-serif');
  const background = document.createElementNS(ns, 'rect');
  background.setAttribute('width', '100%'); background.setAttribute('height', '100%'); background.setAttribute('fill', '#ffffff'); svg.append(background);
  const title = document.createElementNS(ns, 'text');
  title.setAttribute('x', '20'); title.setAttribute('y', '24'); title.setAttribute('font-size', '16'); title.setAttribute('font-weight', 'bold'); title.setAttribute('fill', '#24342b');
  title.textContent = String(chart.title || 'Chart').slice(0, 85); svg.append(title);
  const group = document.createElementNS(ns, 'g'); group.setAttribute('transform', 'translate(0 34)');
  group.append(...[...plot.childNodes].map((child) => child.cloneNode(true))); svg.append(group);
  legend.forEach((entry, index) => {
    const text = document.createElementNS(ns, 'text');
    text.setAttribute('x', String(25 + (index % 3) * 218)); text.setAttribute('y', String(328 + Math.floor(index / 3) * 18));
    text.setAttribute('font-size', '11'); text.setAttribute('fill', entry.color); text.textContent = entry.text.slice(0, 31); svg.append(text);
  });
  const source = new XMLSerializer().serializeToString(svg), bytes = new TextEncoder().encode(source);
  if (bytes.length > 4 * 1024 * 1024) throw new Error('This chart image exceeds 4 MiB.');
  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += 8192) binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
  return { source: `data:image/svg+xml;base64,${btoa(binary)}`, height };
}

function blankWorkbook() {
  const sheetId = id('sheet');
  return {
    id: id('workbook'), name: 'Untitled', appVersion: '1.0.4', locale: LocaleType.EN_US,
    styles: {}, sheetOrder: [sheetId],
    sheets: { [sheetId]: { id: sheetId, name: 'Sheet1', rowCount: 1000, columnCount: 26, cellData: {}, defaultColumnWidth: 96, defaultRowHeight: 22, showGridlines: 1, rowHeader: { width: 46 }, columnHeader: { height: 24 }, zoomRatio: 1 } },
  };
}

/** Create one spreadsheet instance; all API methods use our own stable contract. */
export async function createSpreadsheet(container, { onChange = () => {}, onSelection = () => {} } = {}) {
  if (!container) throw new Error('A spreadsheet container is required.');
  const { univer, univerAPI } = createUniver({
    locale: LocaleType.EN_US,
    theme: greenTheme,
    locales: { [LocaleType.EN_US]: mergeLocales(UniverPresetSheetsCoreEnUS, UniverPresetSheetsDrawingEnUS, UniverPresetSheetsSortEnUS) },
    presets: [UniverSheetsCorePreset({ container, header: false, toolbar: false, formulaBar: false, footer: { sheetBar: true, statisticBar: true, menus: true, zoomSlider: false } }), UniverSheetsDrawingPreset({ allowImageSize: IMAGE_BYTES }), UniverSheetsSortPreset()],
  });
  let workbook = univerAPI.createWorkbook(blankWorkbook());
  const chartRegistry = new WorkbookChartRegistry();
  const imageRegistry = new WorkbookImageRegistry();
  let disposed = false, changeTimer = null, loading = true;
  const subscriptions = [registerLegacyFunctions(univerAPI)];
  // The pinned engine keeps spill results outside ordinary cellData. Read its
  // formula model, not the display interceptor (which rounds displayed values).
  const formulaData = univer.__getInjector().get(FormulaDataModel);
  const arrayValues = sheetId => formulaData.getArrayFormulaCellData()[workbook.getId()]?.[sheetId] || {};
  // Univer 1.0.4 leaves lazy auto-height callbacks alive after their sheet
  // skeleton is disposed. Cancel their public operation IDs before disposal,
  // while the render service can still receive the cancellation operation.
  // There is no completion event. Compact historical IDs into merged per-sheet
  // work after 256 operations so a long editing session does not retain them all.
  const autoHeightTasks = new Map();
  let autoHeightCompactionQueued = false;
  const cancelAutoHeightTasks = (unitId, sheetId) => {
    const tasks = autoHeightTasks.get(unitId);
    if (!tasks) return;
    for (const [taskId, { subUnitId }] of tasks) {
      if (sheetId !== undefined && subUnitId !== sheetId) continue;
      univerAPI.syncExecuteCommand('sheet.operation.cancel-mark-dirty-row-auto-height', { unitId, subUnitId, id: taskId }, { onlyLocal: true });
      tasks.delete(taskId);
    }
    if (!tasks.size) autoHeightTasks.delete(unitId);
  };
  const compactAutoHeightTasks = () => {
    autoHeightCompactionQueued = false;
    if (disposed) return;
    for (const [unitId, tasks] of [...autoHeightTasks]) {
      if (tasks.size <= 256) continue;
      const bySheet = new Map();
      for (const { subUnitId, ranges } of tasks.values()) {
        if (!bySheet.has(subUnitId)) bySheet.set(subUnitId, []);
        bySheet.get(subUnitId).push(...ranges);
      }
      // Native sheet controls can create more sheets than our import limit.
      // One task per sheet is already compact, regardless of the sheet count.
      if (bySheet.size === tasks.size) continue;
      cancelAutoHeightTasks(unitId);
      for (const [subUnitId, ranges] of bySheet) {
        const merged = [];
        for (const range of ranges.sort((left, right) => left.startRow - right.startRow)) {
          const previous = merged.at(-1);
          if (previous && range.startRow <= previous.endRow + 1) previous.endRow = Math.max(previous.endRow, range.endRow);
          else merged.push({ startRow: range.startRow, endRow: range.endRow, startColumn: 0, endColumn: 0 });
        }
        // Recalculation reads the current cell state, including any undo since
        // the original operation. No pending row is lost during compaction.
        univerAPI.syncExecuteCommand('sheet.operation.mark-dirty-row-auto-height', { unitId, subUnitId, id: id('auto-height'), ranges: merged }, { onlyLocal: true });
      }
    }
  };
  const disposeWorkbook = () => {
    if (!workbook) return;
    cancelAutoHeightTasks(workbook.getId());
    univerAPI.disposeUnit(workbook.getId());
    workbook = null;
  };

  const requireWorkbook = () => {
    if (disposed || !workbook) throw new Error('The workbook has been closed.');
    return workbook;
  };
  const sheetById = (sheetId) => {
    const sheet = requireWorkbook().getSheetBySheetId(sheetId || workbook.getActiveSheet().getSheetId());
    if (!sheet) throw new Error('The selected worksheet no longer exists.');
    return sheet;
  };
  const usedSize = (sheet) => {
    let rows = 0, columns = 0;
    sheet.getSheet().getCellMatrix().forValue((row, column, cell) => {
      if (cell && ((cell.v !== null && cell.v !== undefined) || cell.f || cell.p)) {
        rows = Math.max(rows, row + 1); columns = Math.max(columns, column + 1);
      }
    });
    for (const [r, row] of Object.entries(arrayValues(sheet.getSheetId()))) {
      for (const [c, cell] of Object.entries(row || {})) if (cell?.v !== null && cell?.v !== undefined) {
        rows = Math.max(rows, Number(r) + 1); columns = Math.max(columns, Number(c) + 1);
      }
    }
    return { rows, columns };
  };
  const values = (range) => {
    const {startRow, startColumn} = range.getRange();
    const calculated = arrayValues(range.getSheetId());
    return range.getValues(true).map((row, r) => row.map((value, c) =>
      calculated[startRow + r]?.[startColumn + c]?.v ??
      (typeof value?.toPlainText === 'function' ? value.toPlainText() : value ?? null)));
  };
  const settled = () => univerAPI.getFormula().onCalculationResultApplied(10000);
  const getBoundedRange = (sheet, a1) => {
    const used = usedSize(sheet);
    const range = boundedRange(a1, { rows: sheet.getMaxRows(), columns: sheet.getMaxColumns(), usedRows: used.rows, usedColumns: used.columns, sheetName: sheet.getSheetName() });
    return sheet.getRange(range);
  };
  const getSelection = () => {
    const sheet = requireWorkbook().getActiveSheet();
    const selected = sheet.getActiveRange() || sheet.getRange('A1');
    const raw = selected.getRange();
    const primary = sheet.getSelection()?.getCurrentCell();
    const row = primary?.actualRow ?? raw.startRow, column = primary?.actualColumn ?? raw.startColumn;
    const cell = sheet.getRange(row, column);
    const range = { startRow: raw.startRow, endRow: Math.min(raw.endRow, sheet.getMaxRows() - 1), startColumn: raw.startColumn, endColumn: Math.min(raw.endColumn, sheet.getMaxColumns() - 1) };
    return { sheetId: sheet.getSheetId(), sheetName: sheet.getSheetName(), rangeA1: rangeA1(range), ...range, cellA1: rangeA1({ startRow: row, endRow: row, startColumn: column, endColumn: column }), value: values(cell)[0][0], formula: cell.getFormula() || '', row, column };
  };
  const notifySelection = () => {
    if (!disposed && !loading) onSelection(getSelection());
  };
  const selectedContext = () => {
    const selection = getSelection(), sheet = sheetById(selection.sheetId);
    return { selection, sheet, range: getBoundedRange(sheet, selection.rangeA1) };
  };
  const queueChange = () => {
    if (disposed || loading) return;
    clearTimeout(changeTimer);
    changeTimer = setTimeout(() => { changeTimer = null; if (!disposed && !loading) onChange({ sheetId: workbook.getActiveSheet().getSheetId() }); }, 120);
  };
  subscriptions.push(univerAPI.addEvent(univerAPI.Event.CommandExecuted, (event) => {
    if (event.id === 'sheet.operation.mark-dirty-row-auto-height') {
      const { unitId, subUnitId, id: taskId } = event.params;
      if (!autoHeightTasks.has(unitId)) autoHeightTasks.set(unitId, new Map());
      const tasks = autoHeightTasks.get(unitId);
      tasks.set(taskId, { subUnitId, ranges: event.params.ranges.map(({ startRow, endRow }) => ({ startRow, endRow })) });
      // Wait until every command listener has enqueued the original task before
      // canceling it; render services for a newly loaded workbook register later.
      if (tasks.size > 256 && !autoHeightCompactionQueued && tasks.size > new Set([...tasks.values()].map(task => task.subUnitId)).size) {
        autoHeightCompactionQueued = true;
        queueMicrotask(compactAutoHeightTasks);
      }
    } else if (event.id === 'sheet.operation.cancel-mark-dirty-row-auto-height') {
      autoHeightTasks.get(event.params.unitId)?.delete(event.params.id);
    }
    if (event.type === CommandType.MUTATION) {
      // Formula engine bookkeeping/results are derived from the sheet edit; opening
      // an existing project must not become dirty merely because formulas recalc.
      if (!event.id.startsWith('formula.') && event.id !== 'sheet.mutation.set-worksheet-row-auto-height') queueChange();
      queueMicrotask(notifySelection);
    }
  }));
  subscriptions.push(univerAPI.addEvent(univerAPI.Event.BeforeCommandExecute, (event) => {
    if (event.id === 'sheet.mutation.remove-sheet') cancelAutoHeightTasks(event.params.unitId, event.params.subUnitId);
  }));
  subscriptions.push(univerAPI.addEvent(univerAPI.Event.SelectionChanged, notifySelection));
  subscriptions.push(univerAPI.addEvent(univerAPI.Event.ActiveSheetChanged, notifySelection));

  const styleRange = (sheet, range, style = {}) => {
    if (style.fontFamily !== undefined) range.setFontFamily(String(style.fontFamily));
    if (style.fontSize !== undefined) {
      const size = Number(style.fontSize);
      if (!Number.isFinite(size) || size < 6 || size > 200) throw new Error('Font size must be between 6 and 200.');
      range.setFontSize(size);
    }
    if (style.bold !== undefined) range.setFontWeight(style.bold ? 'bold' : 'normal');
    if (style.italic !== undefined) range.setFontStyle(style.italic ? 'italic' : 'normal');
    if (style.underline !== undefined) range.setFontLine(style.underline ? 'underline' : 'none');
    if (style.horizontalAlignment !== undefined) {
      if (!['left', 'center', 'right', 'normal'].includes(style.horizontalAlignment)) throw new Error('Unsupported alignment.');
      range.setHorizontalAlignment(style.horizontalAlignment);
    }
    if (style.verticalAlignment !== undefined) range.setVerticalAlignment(style.verticalAlignment);
    if (style.numberFormat !== undefined) range.setNumberFormat(String(style.numberFormat));
    if (style.fillColor !== undefined) range.setBackgroundColor(String(style.fillColor));
    if (style.textColor !== undefined) range.setFontColor(String(style.textColor));
    if (style.wrap !== undefined) range.setWrap(Boolean(style.wrap));
    if (style.borderBottom) range.setBorder(univerAPI.Enum.BorderType.BOTTOM, univerAPI.Enum.BorderStyleTypes.THIN, typeof style.borderBottom === 'string' ? style.borderBottom : '#999999');
    if (style.merge === true) range.merge();
    if (style.merge === false) range.breakApart();
    if (style.columnWidth !== undefined) {
      const width = Number(style.columnWidth), raw = range.getRange();
      if (!Number.isFinite(width) || width < 24 || width > 1000) throw new Error('Column width must be between 24 and 1000.');
      sheet.setColumnWidths(raw.startColumn, raw.endColumn - raw.startColumn + 1, width);
    }
    if (style.rowHeight !== undefined) {
      const height = Number(style.rowHeight), raw = range.getRange();
      if (!Number.isFinite(height) || height < 16 || height > 1000) throw new Error('Row height must be between 16 and 1000.');
      sheet.setRowHeightsForced(raw.startRow, raw.endRow - raw.startRow + 1, height);
    }
    return true;
  };

  const adapter = {
    getSnapshot() {
      const snapshot = clone(requireWorkbook().save());
      const charts = chartRegistry.snapshot(workbook.getSheets());
      snapshot.custom = { ...(snapshot.custom || {}), statworkbenchActiveSheetId: workbook.getActiveSheet().getSheetId(), statworkbenchCharts: charts, statworkbenchImages: imageRegistry.snapshot(workbook.getSheets(), charts) };
      return snapshot;
    },
    async loadSnapshot(snapshot) {
      const next = snapshot ? validateSnapshot(snapshot) : blankWorkbook();
      const previous = adapter.getSnapshot();
      loading = true;
      clearTimeout(changeTimer);
      changeTimer = null;
      try {
        disposeWorkbook();
        workbook = univerAPI.createWorkbook(next);
        const activeId = next.custom?.statworkbenchActiveSheetId;
        if (activeId && workbook.getSheetBySheetId(activeId)) workbook.setActiveSheet(activeId);
        await settled();
        chartRegistry.restore(next.custom?.statworkbenchCharts,workbook.getSheets());
        imageRegistry.restore(next.custom?.statworkbenchImages,workbook.getSheets());
      } catch (error) {
        disposeWorkbook();
        workbook = univerAPI.createWorkbook(previous);
        chartRegistry.restore(previous.custom?.statworkbenchCharts,workbook.getSheets());
        imageRegistry.restore(previous.custom?.statworkbenchImages,workbook.getSheets());
        throw error;
      } finally { loading = false; }
      queueMicrotask(notifySelection);
      return true;
    },
    getSheets() { return requireWorkbook().getSheets().map((sheet) => ({ id: sheet.getSheetId(), name: sheet.getSheetName(), rowCount: sheet.getMaxRows(), columnCount: sheet.getMaxColumns() })); },
    getActiveSheetId() { return requireWorkbook().getActiveSheet().getSheetId(); },
    selectSheet(sheetId) { requireWorkbook().setActiveSheet(sheetById(sheetId)); notifySelection(); return sheetId; },
    selectRange(sheetId, a1) {
      const sheet = sheetById(sheetId); workbook.setActiveSheet(sheet);
      const range = getBoundedRange(sheet, a1); range.activate();
      const bounds = range.getRange(); sheet.scrollToCell(bounds.startRow, bounds.startColumn, 0);
      notifySelection(); return getSelection();
    },
    getSelection,
    getSelectionStyle() {
      const selection = getSelection(), cell = sheetById(selection.sheetId).getRange(selection.row, selection.column), style = cell.getCellStyleData() || {};
      return {
        bold: style.bl === 1, italic: style.it === 1, underline: style.ul?.s === 1,
        fontFamily: cell.getFontFamily() || 'Arial', fontSize: cell.getFontSize() || 11,
        horizontalAlignment: cell.getHorizontalAlignment(), verticalAlignment: cell.getVerticalAlignment(),
        numberFormat: cell.getNumberFormat() || 'General', fillColor: style.bg?.rgb || '#ffffff', textColor: style.cl?.rgb || '#000000',
      };
    },
    async readRange(sheetId, a1) { await settled(); return values(getBoundedRange(sheetById(sheetId), a1)); },
    async readSheet(sheetId) {
      await settled();
      const sheet = sheetById(sheetId), used = usedSize(sheet);
      if (!used.rows || !used.columns) return [];
      if (used.rows * used.columns > WORKBOOK_LIMITS.cells) throw new Error('The occupied rectangle is too large; select a smaller range.');
      return values(sheet.getRange(0, 0, used.rows, used.columns));
    },
    addMatrix(name, matrix, styles = {}) {
      const data = matrixToCells(matrix);
      if (requireWorkbook().getSheets().length >= WORKBOOK_LIMITS.sheets) throw new Error('A workbook can contain at most 100 worksheets.');
      let storedCells = Object.values(data.cellData).reduce((total, row) => total + Object.keys(row).length, 0);
      for (const existing of workbook.getSheets()) existing.getSheet().getCellMatrix().forValue((_row, _column, cell) => { if (cell) storedCells++; });
      if (storedCells > WORKBOOK_LIMITS.cells) throw new Error('The workbook would exceed 2,000,000 stored cells.');
      const sheetName = uniqueSheetName(name, workbook.getSheets().map((sheet) => sheet.getSheetName()));
      const sheet = workbook.create(sheetName, Math.max(1000, data.rows), Math.max(26, data.columns), { sheet: { cellData: data.cellData, defaultColumnWidth: 110, defaultRowHeight: 22, ...(styles.formatMetadata ? {custom:{statworkbenchFormatMetadata:clone(styles.formatMetadata)}} : {}) } });
      workbook.setActiveSheet(sheet);
      const rules = Array.isArray(styles) ? styles : styles.ranges || [];
      for (const rule of rules) styleRange(sheet, getBoundedRange(sheet, rule.range || rule.a1), rule.style || rule);
      if (styles.headerRows) for (const row of styles.headerRows) if (data.columns) styleRange(sheet, sheet.getRange(row, 0, 1, data.columns), { bold: true, fillColor: '#edf3ef' });
      sheet.getRange('A1').activate();
      queueChange();
      return sheet.getSheetId();
    },
    setCellValue(value, location) {
      const selection = location || getSelection(), sheet = sheetById(selection.sheetId);
      if (!Number.isInteger(selection.row) || selection.row < 0 || selection.row >= sheet.getMaxRows() || !Number.isInteger(selection.column) || selection.column < 0 || selection.column >= sheet.getMaxColumns()) throw new Error('Cell location is outside the worksheet.');
      if (value === null || value === undefined) sheet.getRange(selection.row, selection.column).clearContent();
      else {
        if (!['string', 'number', 'boolean'].includes(typeof value) || (typeof value === 'number' && !Number.isFinite(value))) throw new Error('Enter text, a formula, a finite number, or a boolean.');
        sheet.getRange(selection.row, selection.column).setValue(value);
      }
      notifySelection();
      return true;
    },
    clearSelection() { const sheet = requireWorkbook().getActiveSheet(); (sheet.getActiveRange() || sheet.getRange('A1')).clearContent(); notifySelection(); return true; },
    clearFormatting() { const { range } = selectedContext(); range.clearFormat(); notifySelection(); return true; },
    async fillSelection(direction) {
      if (!['down', 'up', 'left', 'right'].includes(direction)) throw new Error('Choose a fill direction.');
      await adapter.commitEditing();
      const { selection: s, sheet, range } = selectedContext();
      const vertical = direction === 'down' || direction === 'up';
      if (vertical ? s.startRow === s.endRow : s.startColumn === s.endColumn) throw new Error(`Select at least two ${vertical ? 'rows' : 'columns'} to fill ${direction}.`);
      const seed = vertical
        ? sheet.getRange(direction === 'down' ? s.startRow : s.endRow, s.startColumn, 1, s.endColumn - s.startColumn + 1)
        : sheet.getRange(s.startRow, direction === 'right' ? s.startColumn : s.endColumn, s.endRow - s.startRow + 1, 1);
      const success = await seed.autoFill(range, 'COPY');
      if (!success) throw new Error('The selected cells could not be filled.');
      await settled(); notifySelection(); return true;
    },
    async aggregateSelection(name) {
      const operation = String(name).toUpperCase();
      if (!['SUM', 'AVERAGE', 'COUNT', 'MAX', 'MIN'].includes(operation)) throw new Error('Unsupported aggregate formula.');
      await adapter.commitEditing();
      const { selection: s, sheet } = selectedContext();
      let row = s.endRow + 1;
      const spills = arrayValues(s.sheetId);
      for (; row < sheet.getMaxRows(); row++) {
        const cell = sheet.getRange(row, s.startColumn).getCellData();
        if (!spills[row]?.[s.startColumn] && (!cell || ((cell.v === null || cell.v === undefined) && !cell.f && !cell.p))) break;
      }
      if (row >= WORKBOOK_LIMITS.rows) throw new Error('There is no free cell below this range within the worksheet limit.');
      if (row >= sheet.getMaxRows()) sheet.insertRowsAfter(sheet.getMaxRows() - 1, 1);
      const target = sheet.getRange(row, s.startColumn);
      target.setValue({ f: `=${operation}(${s.rangeA1})`, v: null, p: null });
      target.activate(); await settled(); notifySelection();
      return { sheetId: s.sheetId, rangeA1: target.getA1Notation(), value: values(target)[0][0] };
    },
    async sortSelection(ascending = true, { hasHeader = false, column = 0 } = {}) {
      await adapter.commitEditing();
      const { selection: s, sheet } = selectedContext();
      if (!Number.isInteger(column) || column < 0 || column > s.endColumn - s.startColumn) throw new Error('Sort column must lie inside the selected range.');
      const first = s.startRow + (hasHeader ? 1 : 0);
      if (s.endRow - first < 1) throw new Error('Select at least two data rows to sort.');
      sheet.getRange(first, s.startColumn, s.endRow - first + 1, s.endColumn - s.startColumn + 1).sort({ column, ascending: Boolean(ascending) });
      await settled(); notifySelection(); return true;
    },
    mergeSelection(merge = true) {
      const { range } = selectedContext();
      if (merge) range.merge({ defaultMerge: false }); else range.breakApart();
      notifySelection(); return true;
    },
    async insertSelectionRows() {
      await adapter.commitEditing();
      const { selection: s, sheet } = selectedContext(), count = s.endRow - s.startRow + 1;
      if (sheet.getMaxRows() + count > WORKBOOK_LIMITS.rows) throw new Error('The worksheet cannot exceed 100,000 rows.');
      sheet.insertRows(s.startRow, count); return true;
    },
    async deleteSelectionRows() {
      await adapter.commitEditing();
      const { selection: s, sheet } = selectedContext(), count = s.endRow - s.startRow + 1;
      if (count >= sheet.getMaxRows()) throw new Error('A worksheet must retain at least one row.');
      sheet.deleteRows(s.startRow, count); return true;
    },
    async insertSelectionColumns() {
      await adapter.commitEditing();
      const { selection: s, sheet } = selectedContext(), count = s.endColumn - s.startColumn + 1;
      if (sheet.getMaxColumns() + count > WORKBOOK_LIMITS.columns) throw new Error('The worksheet cannot exceed 1,000 columns.');
      sheet.insertColumns(s.startColumn, count); return true;
    },
    async deleteSelectionColumns() {
      await adapter.commitEditing();
      const { selection: s, sheet } = selectedContext(), count = s.endColumn - s.startColumn + 1;
      if (count >= sheet.getMaxColumns()) throw new Error('A worksheet must retain at least one column.');
      sheet.deleteColumns(s.startColumn, count); return true;
    },
    formatSelection(style) { const sheet = requireWorkbook().getActiveSheet(); return styleRange(sheet, sheet.getActiveRange() || sheet.getRange('A1'), style); },
    setRangeStyle(sheetId, a1, style) { const sheet = sheetById(sheetId); return styleRange(sheet, getBoundedRange(sheet, a1), style); },
    async addImage(sheetId, source, { left = 0, top = 0, width, height, native = {}, originalIndex } = {}) {
      const sheet = sheetById(sheetId), position = { left, top, width, height };
      if (![left, top, width, height].every(Number.isFinite) || left < 0 || top < 0 || left > 100000000 || top > 100000000 || width < 1 || height < 1 || width > 20000 || height > 20000 || width * height > 36000000) throw new Error('Unsupported picture dimensions or position.');
      if (!native || typeof native !== 'object' || Array.isArray(native)) throw new Error('Invalid picture metadata.');
      const displaySource = await pictureDisplaySource(source, position, native);
      const anchors = univerAPI.Enum.SheetDrawingAnchorType;
      const kind = native.dynamicMove === false ? anchors.None : native.dynamicSize === false ? anchors.Position : anchors.Both;
      const placement = kind === anchors.None ? { kind, ...position } : { kind, bounds: position };
      let timeout;
      const image = await Promise.race([
        sheet.newOverGridImage().setSource(displaySource, univerAPI.Enum.ImageSourceType.BASE64).setPlacement(placement).buildAsync(),
        new Promise((_resolve, reject) => { timeout = setTimeout(() => reject(new Error('Picture loading timed out.')), 10000); }),
      ]).finally(() => clearTimeout(timeout));
      sheet.insertImages([image]);
      imageRegistry.register(sheetId, image.drawingId, source, position, native, originalIndex, displaySource);
      queueChange(); return image.drawingId;
    },
    async addChart(sheetId, chart, { row = 1, column = 8, width = 680, height, originalIndex } = {}) {
      const sheet = sheetById(sheetId);
      if (!Number.isInteger(row) || row < 0 || row >= WORKBOOK_LIMITS.rows || !Number.isInteger(column) || column < 0 || column >= sheet.getMaxColumns()) throw new Error('Chart position is outside this worksheet.');
      if (!Number.isFinite(width) || width < 160 || width > 2000 || (height !== undefined && (!Number.isFinite(height) || height < 100 || height > 2000))) throw new Error('Unsupported chart image dimensions.');
      const rendered = chartImageSource(chart);
      const requiredRows = row + Math.ceil((height || rendered.height * width / 680) / 22) + 1;
      if (requiredRows > WORKBOOK_LIMITS.rows) throw new Error('There is no space for this chart within the worksheet row limit.');
      if (requiredRows > sheet.getMaxRows()) sheet.insertRowsAfter(sheet.getMaxRows() - 1, requiredRows - sheet.getMaxRows());
      let timeout;
      const image = await Promise.race([
        sheet.newOverGridImage().setSource(rendered.source, univerAPI.Enum.ImageSourceType.BASE64).setColumn(column).setRow(row).setWidth(width).setHeight(height || rendered.height * width / 680).buildAsync(),
        new Promise((_resolve, reject) => { timeout = setTimeout(() => reject(new Error('Chart image loading timed out.')), 10000); }),
      ]).finally(() => clearTimeout(timeout));
      sheet.insertImages([image]);
      chartRegistry.register(sheetId,image.drawingId,chart,{row,column,width,height:height||rendered.height*width/680},rendered.source,originalIndex);
      queueChange();
      return image.drawingId;
    },
    async updateChart(sheetId, drawingId, chart) {
      const sheet=sheetById(sheetId),image=sheet.getImages().find(drawing=>drawing.getId()===drawingId);
      if(!image)throw new Error('This worksheet chart was removed.');
      const rendered=chartImageSource(chart);
      const previous=chartRegistry.snapshot([sheet]).find(entry=>entry.drawingId===drawingId);
      // setSource() in the current image facade mutates its live model before
      // capturing undo. Build a separate drawing so undo retains the old SVG.
      const updated=await image.toBuilder().setPlacement(image.getPlacement()).setSource(rendered.source,univerAPI.Enum.ImageSourceType.BASE64).buildAsync();
      if(!await univerAPI.executeCommand('sheet.command.set-sheet-image',{unitId:workbook.getId(),drawings:[updated]}))throw new Error('The chart image could not be updated.');
      chartRegistry.register(sheetId,drawingId,chart,previous?.position||{},rendered.source,previous?.originalIndex);
      queueChange();return true;
    },
    getChartImages(sheetId) { return sheetById(sheetId).getImages().map((drawing) => drawing.getId()); },
    setZoom(value) { const zoom = Number(value) > 4 ? Number(value) / 100 : Number(value); if (!Number.isFinite(zoom) || zoom < 0.1 || zoom > 4) throw new Error('Zoom must be between 10% and 400%.'); requireWorkbook().getActiveSheet().zoom(zoom); return zoom; },
    getZoom() { return requireWorkbook().getActiveSheet().getZoom(); },
    async commitEditing() {
      await requireWorkbook().endEditingAsync(true);
      await settled();
      if (changeTimer !== null) {
        clearTimeout(changeTimer); changeTimer = null;
        if (!loading) onChange({ sheetId: workbook.getActiveSheet().getSheetId() });
      }
      return true;
    },
    undo() { return univerAPI.undo(); },
    redo() { return univerAPI.redo(); },
    execute(command, params) { requireWorkbook(); return univerAPI.executeCommand(command, params); },
    dispose() { if (disposed) return; disposed = true; clearTimeout(changeTimer); disposeWorkbook(); subscriptions.forEach((subscription) => subscription.dispose()); univer.dispose(); autoHeightTasks.clear(); },
  };
  try {
    if (univerAPI.getCurrentLifecycleStage() < LifecycleStages.Rendered) await new Promise((resolve, reject) => {
      let subscription;
      const timeout = setTimeout(() => { subscription?.dispose(); reject(new Error('Spreadsheet rendering timed out.')); }, 10000);
      subscription = univerAPI.addEvent(univerAPI.Event.LifeCycleChanged, ({ stage }) => {
        if (stage >= LifecycleStages.Rendered) { clearTimeout(timeout); subscription?.dispose(); resolve(); }
      });
    });
    await settled();
  } catch (error) { adapter.dispose(); throw error; }
  loading = false;
  queueMicrotask(notifySelection);
  return adapter;
}
