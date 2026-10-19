const fs=require('node:fs/promises');
const path=require('node:path');
const {randomUUID}=require('node:crypto');
const {validatePreferences}=require('./project.cjs');
const keys=['alpha','decimals','font','fontSize','labels','hideTrailingZeros','scientific','percentProbabilities','timestamp','missingValues','randomSeed','outputMode','language','quickAccess'];
function createPreferencesStore(filename){
 let writes=Promise.resolve();
 return {
  async load(){await writes;try{const text=await fs.readFile(filename,'utf8');if(text.length>16384)throw new Error('Preferences file is too large.');const value=JSON.parse(text);validatePreferences(value);return Object.fromEntries(keys.filter(k=>Object.hasOwn(value,k)).map(k=>[k,value[k]]));}catch(e){if(e.code==='ENOENT')return {};throw e;}},
  async save(value){validatePreferences(value);const next=Object.fromEntries(keys.filter(k=>Object.hasOwn(value,k)).map(k=>[k,value[k]]));const operation=writes.then(async()=>{await fs.mkdir(path.dirname(filename),{recursive:true});const temporary=filename+'.'+randomUUID()+'.writing';try{await fs.writeFile(temporary,JSON.stringify(next,null,2)+'\n',{flag:'wx'});await fs.rename(temporary,filename);}catch(e){await fs.unlink(temporary).catch(()=>{});throw e;}return next;});writes=operation.catch(()=>{});return operation;}
 };
}
module.exports={createPreferencesStore};
