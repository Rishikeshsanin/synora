export const MAX_WAV_BYTES = 32 * 1024 * 1024;
export const MAX_WAV_SECONDS = 180;
const tag = (v, p) => String.fromCharCode(v.getUint8(p), v.getUint8(p+1), v.getUint8(p+2), v.getUint8(p+3));
const put = (v, p, s) => { for (let i=0;i<s.length;i++) v.setUint8(p+i,s.charCodeAt(i)); };
/** @param {ArrayBuffer} buffer */
export function inspectWav(buffer) {
  if (buffer.byteLength < 44 || buffer.byteLength > MAX_WAV_BYTES) throw new Error('WAV must be 44 bytes to 32 MiB.');
  const v = new DataView(buffer);
  if (tag(v,0)!=='RIFF' || tag(v,8)!=='WAVE' || v.getUint32(4,true)+8!==buffer.byteLength) throw new Error('Invalid or truncated RIFF/WAVE file.');
  let format=null, data=null;
  for (let p=12;p<buffer.byteLength;) {
    if (p+8>buffer.byteLength) throw new Error('Truncated WAV chunk.');
    const id=tag(v,p), size=v.getUint32(p+4,true), start=p+8, next=start+size+(size%2);
    if (next>buffer.byteLength) throw new Error('Truncated WAV chunk.');
    if (id==='fmt ') {
      if (format || size<16) throw new Error('Invalid WAV format chunk.');
      const code=v.getUint16(start,true), channels=v.getUint16(start+2,true), rate=v.getUint32(start+4,true), byteRate=v.getUint32(start+8,true), block=v.getUint16(start+12,true), bits=v.getUint16(start+14,true);
      if (code!==1 || bits!==16 || ![1,2].includes(channels) || rate<8000 || rate>48000 || block!==channels*2 || byteRate!==rate*block) throw new Error('Use 16-bit PCM WAV, mono or stereo, 8–48 kHz.');
      format={channels,rate,block};
    } else if (id==='data') {
      if (data) throw new Error('Multiple audio data chunks are unsupported.');
      data={offset:start,size};
    }
    p=next;
  }
  if (!format || !data || !data.size || data.size%format.block) throw new Error('Missing or incomplete PCM audio frames.');
  const frames=data.size/format.block, duration=frames/format.rate;
  if (duration>MAX_WAV_SECONDS) throw new Error('Audio must be at most 180 seconds.');
  return {...format,offset:data.offset,frames,duration};
}
/** @param {ArrayBuffer} buffer @param {{start:number,end:number,fadeIn:number,fadeOut:number}} edit */
export function trimWav(buffer,edit) {
  const info=inspectWav(buffer), {start,end,fadeIn,fadeOut}=edit;
  if (![start,end,fadeIn,fadeOut].every(Number.isFinite) || start<0 || end>info.duration || end<=start || fadeIn<0 || fadeOut<0 || fadeIn+fadeOut>end-start+1e-9) throw new Error('Choose a valid clip range and non-overlapping fades.');
  const first=Math.round(start*info.rate), last=Math.round(end*info.rate), count=last-first;
  if (count<1) throw new Error('Select at least one audio frame.');
  const inFrames=Math.round(fadeIn*info.rate), outFrames=Math.round(fadeOut*info.rate);
  if (inFrames+outFrames>count+1) throw new Error('Fades exceed the selected clip.');
  const size=count*info.block, output=new ArrayBuffer(44+size), dest=new DataView(output), src=new DataView(buffer);
  put(dest,0,'RIFF');dest.setUint32(4,36+size,true);put(dest,8,'WAVE');put(dest,12,'fmt ');dest.setUint32(16,16,true);dest.setUint16(20,1,true);dest.setUint16(22,info.channels,true);dest.setUint32(24,info.rate,true);dest.setUint32(28,info.rate*info.block,true);dest.setUint16(32,info.block,true);dest.setUint16(34,16,true);put(dest,36,'data');dest.setUint32(40,size,true);
  if (!inFrames && !outFrames) new Uint8Array(output,44).set(new Uint8Array(buffer,info.offset+first*info.block,size));
  else for (let i=0;i<count;i++) {
    const gain=Math.min(1,inFrames?i/Math.max(1,inFrames-1):1,outFrames?(count-1-i)/Math.max(1,outFrames-1):1);
    for(let ch=0;ch<info.channels;ch++) dest.setInt16(44+i*info.block+ch*2,Math.round(src.getInt16(info.offset+(first+i)*info.block+ch*2,true)*gain),true);
  }
  return output;
}
