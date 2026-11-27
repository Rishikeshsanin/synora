import test from 'node:test';
import assert from 'node:assert/strict';
import {needsRefresh,validateSignedAsset,downloadPath,fixtureLabel,capabilityState} from './media.mjs';
const now=Date.now(), asset={id:'a',url:'https://example.com/audio?sig=private',expires_at:new Date(now+60000).toISOString()};
test('refresh near expiry, invalid expiry and expired URLs; never refresh local blob',()=>{assert.equal(needsRefresh(asset,now),false);assert.equal(needsRefresh(asset,now+50000),true);assert.equal(needsRefresh({...asset,expires_at:null},now),true);assert.equal(needsRefresh({...asset,expires_at:new Date(now-1).toISOString()},now),true);assert.equal(needsRefresh({url:'blob:demo',expires_at:null},now),false)});
test('signed asset identity and expiry are checked',()=>{assert.equal(validateSignedAsset(asset,'a'),asset);assert.throws(()=>validateSignedAsset(asset,'b'));assert.throws(()=>validateSignedAsset({...asset,expires_at:new Date(now-1).toISOString()},'a'))});
test('download is requested from metadata endpoint, not by changing signature',()=>assert.equal(downloadPath('id/with?chars'),'/v1/assets/id%2Fwith%3Fchars?download=true'));
test('fixture origin stays explicitly labeled',()=>{assert.equal(fixtureLabel(true,true),'Local fixture · Not AI-generated');assert.equal(fixtureLabel(true),'Server fixture · Not AI-generated');assert.equal(fixtureLabel(false),'API output')});
test('capabilities distinguish fixtures, disabled provider and malformed response',()=>{assert.deepEqual(capabilityState({simulated:true,vocals:false}),{simulated:true,available:true});assert.deepEqual(capabilityState({simulated:false,available:false}),{simulated:false,available:false});assert.throws(()=>capabilityState({}))});
