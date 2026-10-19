const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const os=require('node:os');
const path=require('node:path');
const {createFavoritesStore,validateFavorite}=require('../electron/favorites.cjs');
const preset=()=>({name:'Descriptive with plots',id:'1001',ranges:{columns:'Sheet1!A:C'},options:{histogram:true,bins:8},labels:true});
test('favorite configurations survive reload and concurrent mutations',async t=>{
  const directory=await fs.mkdtemp(path.join(os.tmpdir(),'statworkbench-favorites-'));
  t.after(()=>fs.rm(directory,{recursive:true,force:true}));
  const filename=path.join(directory,'favorites.json'),store=createFavoritesStore(filename);
  const [first,second]=await Promise.all([store.save(preset()),store.save({...preset(),name:'Another setup'})]);
  assert.notEqual(first.favoriteId,second.favoriteId);
  assert.equal(first.id,'1001');
  const reloaded=createFavoritesStore(filename);
  assert.equal((await reloaded.list()).length,2);
  assert.deepEqual((await reloaded.list())[0].ranges,{columns:'Sheet1!A:C'});
  await reloaded.delete(first.favoriteId);
  assert.deepEqual((await reloaded.list()).map(x=>x.favoriteId),[second.favoriteId]);
});
test('favorite validation rejects nested executable-shaped data and oversized inputs',()=>{
  assert.throws(()=>validateFavorite({...preset(),id:'unknown'}),/known analysis/);
  assert.throws(()=>validateFavorite({...preset(),options:{x:{unexpected:'object'}}}),/options/);
  assert.throws(()=>validateFavorite({...preset(),options:{x:NaN}}),/options/);
  assert.throws(()=>validateFavorite({...preset(),ranges:JSON.parse('{"__proto__":"A:A"}')}),/ranges/);
  assert.throws(()=>validateFavorite({...preset(),name:'x'.repeat(121)}),/name/);
  assert.throws(()=>validateFavorite({...preset(),labels:'true'}),/labels/);
});
test('recent presets retain last20 complete source configurations across restart',async t=>{
 const directory=await fs.mkdtemp(path.join(os.tmpdir(),'statworkbench-recent-'));t.after(()=>fs.rm(directory,{recursive:true,force:true}));const filename=path.join(directory,'recent.json'),store=createFavoritesStore(filename,{limit:20,trim:true});
 for(let i=0;i<23;i++)await store.save({...preset(),name:'Run '+i,source:{app:'excel',path:'/tmp/synthetic.xlsx',workbook:'synthetic.xlsx',sheet:'Data'}});
 const values=await createFavoritesStore(filename,{limit:20,trim:true}).list();assert.equal(values.length,20);assert.equal(values[0].name,'Run 3');assert.equal(values.at(-1).source.path,'/tmp/synthetic.xlsx');assert.deepEqual(values.at(-1).options,preset().options);
 assert.throws(()=>validateFavorite({...preset(),source:{app:'Finder'}}),/source/);
});
