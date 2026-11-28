import test from 'node:test';
import assert from 'node:assert/strict';
import {inspectWav,trimWav,MAX_WAV_BYTES} from './wav.mjs';
function fixture(channels=1,frames=8000){
  const size=frames*channels*2,b=Buffer.alloc(44+size);b.write('RIFF');b.writeUInt32LE(36+size,4);b.write('WAVEfmt ',8);b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(channels,22);b.writeUInt32LE(8000,24);b.writeUInt32LE(8000*channels*2,28);b.writeUInt16LE(channels*2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(size,40);
  for(let i=44;i<b.length;i+=2)b.writeInt16LE((i-44)%4===0?10000:-10000,i);
  return b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength);
}
const edit={start:0.25,end:0.75,fadeIn:0,fadeOut:0};
test('inspect and trim exact PCM frames, preserve original bytes',()=>{for(const channels of [1,2]){const source=fixture(channels),before=Buffer.from(source).toString('hex');const info=inspectWav(source);assert.equal(info.duration,1);assert.equal(info.channels,channels);const out=trimWav(source,edit),result=inspectWav(out);assert.equal(result.frames,4000);assert.equal(result.channels,channels);assert.deepEqual(new Uint8Array(out,44),new Uint8Array(source,44+2000*channels*2,4000*channels*2));assert.equal(Buffer.from(source).toString('hex'),before)}});
test('fades reach silence at both endpoints and retain stereo separation',()=>{const out=trimWav(fixture(2),{...edit,fadeIn:0.1,fadeOut:0.1}),v=new DataView(out);assert.equal(v.getInt16(44,true),0);assert.equal(v.getInt16(46,true),0);assert.equal(v.getInt16(44+2000*4,true),10000);assert.equal(v.getInt16(46+2000*4,true),-10000);assert.equal(v.getInt16(out.byteLength-2,true),0)});
test('reject malformed, oversized and unsupported WAVs',()=>{const b=fixture();for(const [at,value] of [[20,3],[22,3],[34,24],[32,1]]){const copy=b.slice(0);new DataView(copy).setUint16(at,value,true);assert.throws(()=>inspectWav(copy))}assert.throws(()=>inspectWav(b.slice(0,-1)));assert.throws(()=>inspectWav(new ArrayBuffer(MAX_WAV_BYTES+1)));const copy=b.slice(0);new DataView(copy).setUint32(40,0xffffffff,true);assert.throws(()=>inspectWav(copy))});
test('reject invalid ranges and overlapping fades',()=>{for(const patch of [{start:-1},{end:2},{end:0.25},{fadeIn:0.4,fadeOut:0.4},{fadeIn:NaN},{start:0.5,end:0.50000001}])assert.throws(()=>trimWav(fixture(),{...edit,...patch}))});
test('parse padded unknown metadata chunks and remove them from export',()=>{const raw=new Uint8Array(fixture()),out=new Uint8Array(raw.length+10);out.set(raw.slice(0,36));out.set([74,85,78,75,1,0,0,0,99,0],36);out.set(raw.slice(36),46);new DataView(out.buffer).setUint32(4,out.length-8,true);assert.equal(inspectWav(out.buffer).offset,54);assert.equal(inspectWav(trimWav(out.buffer,edit)).offset,44)});
