// SPDX-License-Identifier: MIT
// Apply an independently converted original workbook without shifting cells.
export async function loadOriginalWorkbook(book, data) {
  if (!data?.workbook) throw new Error('The import does not contain a workbook.');
  const notes = [...(data.notes || [])];
  const failedCharts = new Set();
  const failedImages = new Map();
  await book.loadSnapshot(data.workbook);
  for (const imported of data.importedImages || data.workbook.custom?.statplusImport?.importedImages || []) {
    try {
      await book.addImage(imported.sheetId, imported.source, {...imported.position,native:imported.native,originalIndex:imported.originalIndex});
    } catch (error) {
      if(!failedImages.has(imported.sheetId))failedImages.set(imported.sheetId,new Set());
      failedImages.get(imported.sheetId).add(imported.originalIndex);
      notes.push(`Picture ${imported.originalIndex + 1} could not be displayed: ${error.message}`);
    }
  }
  for (const imported of data.importedCharts || []) {
    try {
      await book.addChart(imported.sheetId, imported.chart, {...imported.position,originalIndex:imported.originalIndex});
    } catch (error) {
      failedCharts.add(imported.originalIndex);
      notes.push(`Chart ${imported.originalIndex + 1} could not be displayed: ${error.message}`);
    }
  }
  if(failedCharts.size||failedImages.size){
    // An image decoder failure is not a user deletion. Retain the original
    // native chart on export even though its converted image never appeared.
    const snapshot=book.getSnapshot(),provenance=snapshot.custom?.statplusImport;
    if(Array.isArray(provenance?.managedChartIndices)){
      provenance.managedChartIndices=provenance.managedChartIndices.filter(index=>!failedCharts.has(index));
    }
    for(const [sheetId,indices] of failedImages){
      const sheetProvenance=snapshot.sheets?.[sheetId]?.custom?.statplusImport;
      if(Array.isArray(sheetProvenance?.managedImageIndices))sheetProvenance.managedImageIndices=sheetProvenance.managedImageIndices.filter(index=>!indices.has(index));
    }
    await book.loadSnapshot(snapshot);
  }
  const active = data.workbook.custom?.statworkbenchActiveSheetId;
  if (active) await book.selectSheet(active);
  return notes;
}
