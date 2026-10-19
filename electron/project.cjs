// SPDX-License-Identifier: MIT
function validatePreferences(prefs) {
 if(prefs===undefined)return;
 if(!prefs||typeof prefs!=='object'||Array.isArray(prefs))throw new Error('Invalid workbook preferences.');
 if(prefs.alpha!==undefined&&(!Number.isFinite(prefs.alpha)||prefs.alpha<=0||prefs.alpha>=1))throw new Error('Invalid significance level.');
 if(prefs.decimals!==undefined&&(!Number.isInteger(prefs.decimals)||prefs.decimals<0||prefs.decimals>15))throw new Error('Invalid report decimal places.');
 if(prefs.fontSize!==undefined&&(!Number.isFinite(prefs.fontSize)||prefs.fontSize<6||prefs.fontSize>72))throw new Error('Invalid report font size.');
 if(prefs.font!==undefined&&(typeof prefs.font!=='string'||prefs.font.length>100))throw new Error('Invalid report font.');
 if(prefs.labels!==undefined&&typeof prefs.labels!=='boolean')throw new Error('Invalid label setting.');
 for(const key of ['hideTrailingZeros','scientific','percentProbabilities','timestamp'])if(prefs[key]!==undefined&&typeof prefs[key]!=='boolean')throw new Error('Invalid output preference.');
 if(prefs.missingValues!==undefined&&!['automatic','casewise'].includes(prefs.missingValues))throw new Error('Invalid missing-values setting.');
 if(prefs.randomSeed!==undefined&&(!Number.isSafeInteger(prefs.randomSeed)||prefs.randomSeed<0||prefs.randomSeed>4294967295))throw new Error('Invalid random seed.');
 if(prefs.outputMode!==undefined&&!['worksheet','workbook'].includes(prefs.outputMode))throw new Error('Invalid output mode.');
 if(prefs.quickAccess!==undefined&&(!Array.isArray(prefs.quickAccess)||prefs.quickAccess.length>20||!prefs.quickAccess.every(key=>typeof key==='string'&&/^(analysis:(?:[0-9]{4,5}|copula\.bivariate)|category:[A-Za-z /-]+)$/.test(key))))throw new Error('Invalid Quick Access Toolbar configuration.');
 if(prefs.language!==undefined&&prefs.language!=='en')throw new Error('This language is not installed.');
}
function validateResults(items){
  for (const item of items) {
    if (!item || typeof item.id !== 'string' || !item.result || !Array.isArray(item.result.tables) || !Array.isArray(item.result.charts)) throw new Error('Invalid analysis result in project.');
    if (!item.result.tables.every(t=>t && Array.isArray(t.columns) && Array.isArray(t.rows) && t.rows.every(Array.isArray))) throw new Error('Invalid result table in project.');
    if (!item.result.charts.every(c=>c && Array.isArray(c.series) && c.series.every(s=>s && Array.isArray(s.y)))) throw new Error('Invalid result chart in project.');
    for(const key of ['notes','warnings'])if(item.result[key]!==undefined&&!Array.isArray(item.result[key]))throw new Error('Invalid result annotations.');
  }
}
function validateProject(project) {
  if(!project||typeof project!=='object'||JSON.stringify(project).length>64*1024*1024)throw new Error('Invalid project size.');
  validatePreferences(project.preferences);
  if (project?.format === 'statworkbench' && project.version === 2) {
    const workbook=project.workbook;
    if (!workbook || typeof workbook !== 'object' || !Array.isArray(workbook.sheetOrder) || !workbook.sheetOrder.length || new Set(workbook.sheetOrder).size!==workbook.sheetOrder.length || workbook.sheetOrder.length>100 || !workbook.sheets || typeof workbook.sheets !== 'object') throw new Error('Invalid workbook project.');
    let cells=0;
    for(const id of workbook.sheetOrder) {
      const sheet=workbook.sheets[id];
      if(!sheet || typeof sheet.name !== 'string' || !Number.isInteger(sheet.rowCount) || sheet.rowCount<1 || sheet.rowCount>100000 || !Number.isInteger(sheet.columnCount) || sheet.columnCount<1 || sheet.columnCount>1000) throw new Error('Invalid worksheet dimensions.');
      for(const [row,columns] of Object.entries(sheet.cellData || {})) {
        if(!/^\d+$/.test(row) || Number(row)>=sheet.rowCount || !columns || typeof columns !== 'object') throw new Error('Invalid worksheet cells.');
        for(const [column,cell] of Object.entries(columns)) {
          if(!/^\d+$/.test(column) || Number(column)>=sheet.columnCount || (cell!==null&&(!cell || typeof cell !== 'object'))) throw new Error('Invalid worksheet cell.');
          if(cell===null)continue;
          if(cell.v!==undefined&&cell.v!==null&&!['string','number','boolean'].includes(typeof cell.v))throw new Error('Invalid cell value.');
          if(typeof cell.v==='number'&&!Number.isFinite(cell.v))throw new Error('Invalid numeric cell.');
          if(cell.f!==undefined&&cell.f!==null&&typeof cell.f!=='string')throw new Error('Invalid formula.');
          if(++cells>2000000)throw new Error('Project exceeds two million populated cells.');
        }
      }
    }
    if(!Array.isArray(project.results)||project.results.length>200)throw new Error('Invalid project analyses.');
    validateResults(project.results);
    return project;
  }
  if (!project || project.format !== 'statworkbench' || project.version !== 1 || !Array.isArray(project.sheets) || project.sheets.length < 1 || project.sheets.length > 100) throw new Error('This is not a supported StatWorkbench project.');
  for (const sheet of project.sheets) {
    if (!sheet || typeof sheet.name !== 'string' || !Array.isArray(sheet.columns) || !sheet.columns.length || !Array.isArray(sheet.rows) || sheet.columns.length > 1000 || sheet.rows.length > 100000 || sheet.columns.length*sheet.rows.length > 2000000) throw new Error('Invalid worksheet in project.');
    if (!sheet.columns.every(c => typeof c === 'string' && c.trim().length > 0 && c.length <= 1024) || new Set(sheet.columns).size !== sheet.columns.length || !sheet.rows.every(r => Array.isArray(r) && r.length <= sheet.columns.length && r.every(v => v === null || typeof v === 'number' && Number.isFinite(v) || ['string','boolean'].includes(typeof v)))) throw new Error('Project cells or headers are invalid.');
  }
  if (!Array.isArray(project.results) || project.results.length > 200) throw new Error('Invalid project results.');
  if (project.active !== undefined && (!Number.isInteger(project.active) || project.active < 0 || project.active >= project.sheets.length)) throw new Error('Invalid active worksheet.');
  validateResults(project.results);
  return project;
}

module.exports={validateProject,validatePreferences};
