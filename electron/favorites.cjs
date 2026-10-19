const fs = require('node:fs/promises');
const path = require('node:path');
const {randomUUID} = require('node:crypto');
const knownProcedures = new Set([...require('./procedures.json'),...require('./extension-procedures.json')].map(item => item.id));
const plainObject = value => value && typeof value === 'object' && !Array.isArray(value) && [Object.prototype, null].includes(Object.getPrototypeOf(value));
const safeKey = key => key.length > 0 && key.length <= 200 && !['__proto__','constructor','prototype'].includes(key);
function optionValue(value) {
  if (value === null || typeof value === 'boolean') return true;
  if (typeof value === 'number') return Number.isFinite(value);
  if (typeof value === 'string') return value.length <= 10000;
  return Array.isArray(value) && value.length <= 1000 && value.every(item => !Array.isArray(item) && optionValue(item));
}
function validateFavorite(input, persisted = false) {
  if (!plainObject(input) || typeof input.name !== 'string' || !input.name.trim() || input.name.trim().length > 120 || !knownProcedures.has(input.id)) throw new Error('A favorite needs a name and a known analysis.');
  if (!plainObject(input.options) || Object.keys(input.options).length > 300 || !Object.entries(input.options).every(([key,value])=>safeKey(key)&&optionValue(value))) throw new Error('Favorite options are invalid or too large.');
  if (!plainObject(input.ranges) || Object.keys(input.ranges).length > 100 || !Object.entries(input.ranges).every(([key,value])=>safeKey(key)&&typeof value==='string'&&value.length<=10000)) throw new Error('Favorite ranges are invalid or too large.');
  if (typeof input.labels !== 'boolean') throw new Error('Favorite labels setting must be true or false.');
  const record = {name:input.name.trim(),id:input.id,options:input.options,ranges:input.ranges,labels:input.labels};
  if(input.source!==undefined){const source=input.source;if(!plainObject(source)||!['standalone','excel','numbers'].includes(source.app))throw new Error('Invalid favorite data source.');record.source={app:source.app};for(const key of ['path','workbook','sheet'])if(source[key]!==undefined){if(typeof source[key]!=='string'||source[key].length>4096||source[key].includes('\0'))throw new Error('Invalid favorite source reference.');record.source[key]=source[key];}}
  if (persisted) {
    if (typeof input.favoriteId !== 'string' || !/^[a-f0-9-]{36}$/i.test(input.favoriteId)) throw new Error('Invalid saved favorite identifier.');
    record.favoriteId = input.favoriteId;
  }
  if (Buffer.byteLength(JSON.stringify(record)) > 256 * 1024) throw new Error('Favorite exceeds 256 KB.');
  return JSON.parse(JSON.stringify(record));
}
function createFavoritesStore(filename,{limit=200,trim=false}={}) {
  let updates = Promise.resolve();
  async function read() {
    let content;
    try {
      const stat = await fs.stat(filename);
      if (stat.size > 8 * 1024 * 1024) throw new Error('Saved favorites exceed the 8 MB limit.');
      content = await fs.readFile(filename,'utf8');
    } catch (error) {if(error.code==='ENOENT')return [];throw error;}
    const data = JSON.parse(content);
    if (!data || data.version !== 1 || !Array.isArray(data.favorites) || data.favorites.length > 200) throw new Error('Invalid saved favorites file.');
    const records = data.favorites.map(item=>validateFavorite(item,true));
    if(new Set(records.map(item=>item.favoriteId)).size!==records.length)throw new Error('Duplicate favorite identifiers.');
    return records;
  }
  async function write(records) {
    const text=JSON.stringify({version:1,favorites:records},null,2)+'\n';
    if(Buffer.byteLength(text)>8*1024*1024)throw new Error('Saved favorites exceed the 8 MB limit.');
    await fs.mkdir(path.dirname(filename),{recursive:true});
    const temporary=filename+'.'+randomUUID()+'.writing';
    try {await fs.writeFile(temporary,text,{flag:'wx'});await fs.rename(temporary,filename);} catch(error){await fs.unlink(temporary).catch(()=>{});throw error;}
  }
  function mutate(operation) {const result=updates.then(operation);updates=result.catch(()=>{});return result;}
  return {
    async list(){await updates;return read();},
    save(input){const record=validateFavorite(input);return mutate(async()=>{const records=await read();if(records.length>=limit&&!trim)throw new Error('You can save up to '+limit+' favorites.');if(trim)while(records.length>=limit)records.shift();record.favoriteId=randomUUID();records.push(record);await write(records);return record;});},
    delete(favoriteId){if(typeof favoriteId!=='string'||!/^[a-f0-9-]{36}$/i.test(favoriteId))throw new Error('Choose a saved favorite.');return mutate(async()=>{const records=await read();const next=records.filter(item=>item.favoriteId!==favoriteId);if(next.length===records.length)throw new Error('Favorite not found.');await write(next);return true;});},
  };
}
module.exports={createFavoritesStore,validateFavorite};
