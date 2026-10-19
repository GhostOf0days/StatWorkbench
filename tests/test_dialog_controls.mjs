import test from 'node:test';
import assert from 'node:assert/strict';
import {controlEnabled,numericOptionError} from '../renderer/dialog-controls.js';

test('manual distribution parameters follow inverse and nested dependencies',()=>{
 const layout={histogram:{},normal:{parent:'histogram'},estimate:{parent:'histogram'},mean:{parent:'estimate',parentInverse:true}};
 assert.equal(controlEnabled('normal',{histogram:false},layout),false);
 assert.equal(controlEnabled('mean',{histogram:false,estimate:false},layout),false);
 assert.equal(controlEnabled('mean',{histogram:true,estimate:true},layout),false);
 assert.equal(controlEnabled('mean',{histogram:true,estimate:false},layout),true);
});
test('interval validator permits automatic or at least three bins',()=>{
 const f={label:'Intervals',type:'integer'},layout={validator:'0,3-'};
 for(const n of [0,3,10,1000])assert.equal(numericOptionError(f,n,layout),null);
 for(const n of [-1,1,2,3.5,Infinity])assert.ok(numericOptionError(f,n,layout));
});
test('finite range validators and integer cell references are distinct',()=>{
 const f={label:'Count',type:'integer'},layout={validator:'2-100'};
 assert.equal(numericOptionError(f,100,layout),null);assert.ok(numericOptionError(f,101,layout));
 assert.equal(numericOptionError(f,"'Data'!B2",{cellReference:true}),null);
 assert.ok(numericOptionError(f,'not a number',{}));
});
test('a zero-valued mode disables dependent parameters, including inverse modes',()=>{
 const layout={lag:{},p:{parent:'lag'},automatic:{parent:'lag',parentInverse:true}};
 assert.equal(controlEnabled('p',{lag:'0'},layout),false);
 assert.equal(controlEnabled('automatic',{lag:'0'},layout),true);
 assert.equal(controlEnabled('p',{lag:'1'},layout),true);
});
