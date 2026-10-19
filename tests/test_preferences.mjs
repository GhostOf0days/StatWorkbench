import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
import {DEFAULT_PREFERENCES,safePreferences,numberFormat,formatNumber,isProbabilityLabel} from '../renderer/preferences.mjs';
const {createPreferencesStore}=createRequire(import.meta.url)('../electron/preferences.cjs');
test('documented output preferences retain full numerical values and match display examples',()=>{
 assert.equal(DEFAULT_PREFERENCES.decimals,5);
 assert.equal(formatNumber(100.5,numberFormat({...DEFAULT_PREFERENCES,decimals:4})),'100.5000');
 assert.equal(formatNumber(100.5,numberFormat({...DEFAULT_PREFERENCES,decimals:4,hideTrailingZeros:true})),'100.5');
 assert.equal(formatNumber(8675309,numberFormat({...DEFAULT_PREFERENCES,decimals:3,scientific:true})),'8.675E+06');
 assert.equal(formatNumber(.0123,numberFormat({...DEFAULT_PREFERENCES,decimals:2,percentProbabilities:true},{probability:true})),'1.23%');
 assert.equal(formatNumber(2,numberFormat({...DEFAULT_PREFERENCES,decimals:15})), '2.000000000000000');
 assert.equal(isProbabilityLabel('p'),true);assert.equal(isProbabilityLabel('p-value'),true);assert.equal(isProbabilityLabel('Sample size'),false);
});
test('preferences survive restart and reject invalid global settings',async()=>{
 const folder=await mkdtemp(path.join(os.tmpdir(),'statworkbench-prefs-test-'));try{
 const filename=path.join(folder,'prefs.json');const store=createPreferencesStore(filename);assert.deepEqual(await store.load(),{});
 const value={...DEFAULT_PREFERENCES,missingValues:'casewise',randomSeed:17,decimals:15,scientific:true,outputMode:'workbook'};
 await store.save(value);assert.deepEqual(await createPreferencesStore(filename).load(),value);
 await assert.rejects(store.save({...value,randomSeed:-1}),/seed/);await assert.rejects(store.save({...value,language:'unsupported'}),/language/);
 assert.equal(safePreferences({decimals:999,alpha:2}).decimals,5);
 }finally{await rm(folder,{recursive:true,force:true});}
});
