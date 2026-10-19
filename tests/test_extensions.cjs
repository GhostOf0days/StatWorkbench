const test=require('node:test');
const assert=require('node:assert/strict');
const {validateFavorite}=require('../electron/favorites.cjs');
const {validatePreferences}=require('../electron/project.cjs');
const {validateLaunchRequest}=require('../electron/excel-addin.cjs');
const extensions=require('../electron/extension-procedures.json');
test('independent extensions are present in the shared desktop command catalog',()=>{
  const expected=['copula.bivariate','dependence.association','dependence.partial','dependence.distance','dependence.mutual_information','dependence.tail_coexceedance','dependence.lead_lag','stochastic.markov_chain'];
  assert.deepEqual(extensions.map(item=>item.id),expected);
  assert.equal(new Set(extensions.map(item=>item.name)).size,expected.length);
  for(const item of extensions){
    assert.equal(validateFavorite({name:item.name,id:item.id,ranges:{},options:{},labels:true}).id,item.id);
    assert.equal(validateLaunchRequest({version:1,requestId:'ac3fa1dd-e035-4bb2-8d11-cd9be1fdbb92',createdAt:Date.now(),command:`analysis:${item.id}`,excelProcessId:1234,workbook:'Synthetic.xlsx',sheet:'Data',rangeA1:'A1:B50'}).command,`analysis:${item.id}`);
  }
});
test('copula commands persist in favorites, toolbar preferences and Excel handoffs',async()=>{
  const {safePreferences}=await import('../renderer/preferences.mjs');
  const shortcut={quickAccess:['analysis:copula.bivariate','category:Dependence models']};
  validatePreferences(shortcut);
  assert.deepEqual(safePreferences(shortcut).quickAccess,shortcut.quickAccess);
  const favorite={name:'Joint tail model',id:'copula.bivariate',ranges:{x:'Data!A:A',y:'Data!B:B'},options:{family:'student',samples:100,seed:17},labels:true};
  assert.equal(validateFavorite(favorite).id,favorite.id);
  const now=Date.now();
  assert.equal(validateLaunchRequest({version:1,requestId:'ac3fa1dd-e035-4bb2-8d11-cd9be1fdbb92',createdAt:now,command:'analysis:copula.bivariate',excelProcessId:1234,workbook:'Synthetic.xlsx',sheet:'Data',rangeA1:'A1:B50'},{now}).command,'analysis:copula.bivariate');
  assert.throws(()=>validateFavorite({...favorite,id:'copula.unknown'}),/known analysis/);
});
