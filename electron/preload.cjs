const {contextBridge, ipcRenderer} = require('electron');
contextBridge.exposeInMainWorld('workbench', Object.freeze({
  environment: {desktop:true,platform:process.platform},
  catalog: () => ipcRenderer.invoke('engine:catalog'),
  analyze: params => ipcRenderer.invoke('engine:analyze', params),
  importData: options => ipcRenderer.invoke('file:import', options || {}),
  exportData: data => ipcRenderer.invoke('file:export', data),
  exportOriginalProject: workbook => ipcRenderer.invoke('project:export-original', workbook),
  clearProjectSource: () => ipcRenderer.invoke('project:clear-source'),
  saveProject: project => ipcRenderer.invoke('project:save', project),
  openProject: () => ipcRenderer.invoke('project:open'),
  saveReport: html => ipcRenderer.invoke('report:save', html),
  loadPreferences: () => ipcRenderer.invoke('preferences:load'),
  savePreferences: value => ipcRenderer.invoke('preferences:save', value),
  listSpreadsheets: () => ipcRenderer.invoke('spreadsheet:list'),
  takeExcelCommand: () => ipcRenderer.invoke('excel-addin:take'),
  externalSpreadsheet: request => ipcRenderer.invoke('spreadsheet:request', request),
  setSpreadsheetSource: source => ipcRenderer.invoke('spreadsheet:source', source),
  openFavoriteSource: id => ipcRenderer.invoke('favorites:source',id),
  listRecent: () => ipcRenderer.invoke('recent:list'),
  rememberAnalysis: value => ipcRenderer.invoke('recent:save',value),
  openRecentSource: id => ipcRenderer.invoke('recent:source',id),
  listFavorites: () => ipcRenderer.invoke('favorites:list'),
  saveFavorite: favorite => ipcRenderer.invoke('favorites:save', favorite),
  deleteFavorite: favoriteId => ipcRenderer.invoke('favorites:delete', favoriteId),
  setDirty: dirty => ipcRenderer.send('project:dirty', Boolean(dirty)),
  onMenu: callback => {
    const handler = (_, action) => callback(action);
    ipcRenderer.on('menu:action', handler);
    return () => ipcRenderer.removeListener('menu:action', handler);
  }
}));
