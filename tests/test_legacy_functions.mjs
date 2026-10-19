import test from 'node:test';
import assert from 'node:assert/strict';
import { isoCeiling, euro, euroConvert, amorDegrc, legacyArray, registerLegacyFunctions } from '../renderer/legacy-functions.mjs';

test('ISO.CEILING handles signs, zero and decimal multiples', () => {
  for (const [args, expected] of [[[4.3],5],[[-4.3,2],-4],[[-4.3,-2],-4],[[4.3,0],0],[[.3,.1],.3]])
    assert(Math.abs(isoCeiling(...args)-expected) < 1e-14);
  assert.equal(isoCeiling('#REF!'), '#REF!');
  assert.equal(isoCeiling('bad'), '#VALUE!');
  assert.equal(isoCeiling([[1,2]]), '#VALUE!');
});

test('legacy EURO and EUROCONVERT preserve observed rate rounding', () => {
  assert.equal(euro('DEM'),1.96);
  assert.equal(euro('FRF-extra'),6.56);
  assert.equal(euro('dem'),'#NUM!');
  assert.equal(euroConvert(1.2,'DEM','EUR'),.61);
  assert.equal(euroConvert(1,'FRF','DEM',true),1/6.56*1.96);
  assert.equal(euroConvert(1,'FRF','DEM',true,3),1/6.56*1.956);
  assert.equal(euroConvert(1.234,'DEM','DEM'),1.234);
  assert.equal(euroConvert(1,'DEM','USD'),'#VALUE!');
  assert.equal(euroConvert(1,'DEM','EUR',true,2),'#VALUE!');
  assert.equal(euroConvert(1,'DEM','EUR','FALSE'),.51);
});

test('AMORDEGRC matches published depreciation examples and error domains', () => {
  // Microsoft example: cost2400, 19Aug2008–31Dec2008, salvage300, rate15%.
  assert.equal(amorDegrc(2400,39679,39813,300,0,.15,1),330);
  assert.equal(amorDegrc(2400,39679,39813,300,1,.15,1),776);
  // LibreOffice example: cost2000, 1Feb2020–31Dec2020, salvage10, period4.
  assert.equal(amorDegrc(2000,43862,44196,10,4,.1,0),163);
  assert.deepEqual(Array.from({length:8},(_,i)=>amorDegrc(2400,39679,39813,300,i,.15,1)),[330,776,485,303,190,158,0,0]);
  for (const rate of [0,-1,2,.8,.4,.22]) assert.equal(amorDegrc(2400,39679,39813,300,1,rate,1),'#NUM!');
  assert.equal(amorDegrc(2400,39814,39813,300,1,.15,1),'#NUM!');
  assert.equal(amorDegrc(2400,39679,39813,300,1,.15,2),'#NUM!');
  assert.equal(amorDegrc(2400,39679,39813,300,100001,.15,1),'#NUM!');
  assert.equal(amorDegrc('bad',39679,39813,300,1,.15,1),'#VALUE!');
});

test('registrations dispose exactly once', () => {
  const names=[], disposed=[];
  const registration=registerLegacyFunctions({getFormula:()=>({registerFunction(name,fn){names.push(name);assert.equal(typeof fn,'function');return{dispose:()=>disposed.push(name)};}})});
  assert.deepEqual(names,['ISO.CEILING','EURO','EUROCONVERT','AMORDEGRC','SWB.CSE']);
  registration.dispose();registration.dispose();assert.deepEqual(disposed,names);
});

test('legacy array evaluates once then broadcasts, crops and pads its result', () => {
  assert.deepEqual(legacyArray([[1,2],[3,4]],3,3),[[1,2,'#N/A'],[3,4,'#N/A'],['#N/A','#N/A','#N/A']]);
  assert.deepEqual(legacyArray([[1],[2]],2,3),[[1,1,1],[2,2,2]]);
  assert.deepEqual(legacyArray([[1,2]],3,1),[[1],[1],[1]]);
  assert.deepEqual(legacyArray(.1234567890123456,2,2),[[.1234567890123456,.1234567890123456],[.1234567890123456,.1234567890123456]]);
  assert.equal(legacyArray(1,100001,1),'#NUM!');
  assert.equal(legacyArray(1,100000,1000),'#NUM!');
});
