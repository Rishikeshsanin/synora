"use client";
import {useEffect,useRef,useState} from "react";
import {Button,Section} from "../../../packages/ui";
import {inspectWav,trimWav,MAX_WAV_BYTES} from "../lib/wav.mjs";
type Source={name:string;buffer:ArrayBuffer;info:ReturnType<typeof inspectWav>};
type Edit={start:string;end:string;fadeIn:string;fadeOut:string};
type Preview={url:string;duration:number;bytes:number};
const initial:Edit={start:"0",end:"0",fadeIn:"0",fadeOut:"0"};
const fields=[["start","Clip start (seconds)"],["end","Clip end (seconds)"],["fadeIn","Fade in (seconds)"],["fadeOut","Fade out (seconds)"]] as const;
export default function AudioWorkshop(){
 const [source,setSource]=useState<Source|null>(null),[edit,setEdit]=useState<Edit>(initial),[preview,setPreview]=useState<Preview|null>(null),[error,setError]=useState(""),[loading,setLoading]=useState(false),[rights,setRights]=useState(false);
 const resources=useRef<{version:number;url:string|null}>({version:0,url:null});
 useEffect(()=>{const allocated=resources.current;return()=>{allocated.version++;if(allocated.url)URL.revokeObjectURL(allocated.url);allocated.url=null}},[]);
 function clearPreview(){const r=resources.current;if(r.url)URL.revokeObjectURL(r.url);r.url=null;setPreview(null)}
 function reset(){resources.current.version++;clearPreview();setSource(null);setEdit(initial);setError("");setLoading(false);setRights(false)}
 async function importFile(file:File){
  reset();const version=resources.current.version;setLoading(true);
  try{if(file.size>MAX_WAV_BYTES)throw Error("Choose a WAV file of at most 32 MiB.");const buffer=await file.arrayBuffer();const info=inspectWav(buffer);if(resources.current.version!==version)return;setSource({name:file.name,buffer,info});setEdit({...initial,end:String(info.duration)})}
  catch(e){if(resources.current.version===version)setError(e instanceof Error?e.message:"Could not read WAV.")}
  finally{if(resources.current.version===version)setLoading(false)}
 }
 function update(key:keyof Edit,value:string){clearPreview();setError("");setEdit(e=>({...e,[key]:value}))}
 function renderClip(){
  if(!source||!rights)return;
  clearPreview();setError("");
  try{if(Object.values(edit).some(value=>!value.trim()))throw Error("Complete all four time fields.");const buffer=trimWav(source.buffer,{start:Number(edit.start),end:Number(edit.end),fadeIn:Number(edit.fadeIn),fadeOut:Number(edit.fadeOut)});const info=inspectWav(buffer);const url=URL.createObjectURL(new Blob([buffer],{type:"audio/wav"}));resources.current.url=url;setPreview({url,duration:info.duration,bytes:buffer.byteLength})}
  catch(e){setError(e instanceof Error?e.message:"Could not render clip.")}
 }
 const length=Number(edit.end)-Number(edit.start);
 return <div className="workshop"><Section title="Cut a moment from your sound" detail="Local audio editing · no AI inference or upload">
  <p>Turn a longer WAV into a short intro, soundtrack cue or social clip. Import an exported track or your own audio, choose an exact range, and add smooth fades. Your original stays unchanged.</p>
  <label htmlFor="workshop-file">Import PCM WAV</label><input id="workshop-file" type="file" accept=".wav,audio/wav,audio/wave,audio/x-wav" onChange={e=>{const file=e.target.files?.[0];e.target.value="";if(file)void importFile(file)}}/>
  <p className="fine workshop-note">16-bit PCM WAV · mono or stereo · 8–48 kHz · up to 180 seconds and 32 MiB. Files are processed in this tab only and cleared when you leave the workshop.</p>
  {loading&&<p role="status">Reading local audio…</p>}
  {source&&<><div className="workshop-source"><div><strong>{source.name}</strong><p className="fine">{source.info.duration.toFixed(3)}s · {source.info.rate/1000} kHz · {source.info.channels===1?"Mono":"Stereo"}</p></div><Button className="secondary" onClick={reset}>Clear file</Button></div>
   <form onSubmit={e=>{e.preventDefault();renderClip()}}><div className="workshop-fields">{fields.map(([key,label])=><div key={key}><label htmlFor={"workshop-"+key}>{label}</label><input id={"workshop-"+key} type="number" required min="0" max={source.info.duration} step="any" value={edit[key]} onChange={e=>update(key,e.target.value)}/></div>)}</div>
   <p className="fine">Selected duration: {Number.isFinite(length)&&length>0?length.toFixed(3)+"s":"—"} · fades cannot overlap.</p>
   <label className="check"><input type="checkbox" checked={rights} onChange={e=>{clearPreview();setRights(e.target.checked)}}/> I own or have permission to edit this audio.</label>
   <Button className="primary" type="submit" disabled={!rights}>Render local clip</Button></form></>}
  {error&&<p role="alert" className="notice">{error}</p>}
 </Section><Section title="Clip preview" detail="Lossless PCM export · no change to sample rate or channels">
 {preview?<div className="player"><p role="status">{preview.duration.toFixed(3)}s · {(preview.bytes/1024).toFixed(1)} KiB</p><audio controls preload="metadata" aria-label="Clip playback" src={preview.url}/><div><a className="button primary" href={preview.url} download="synora-local-clip.wav">Download WAV clip</a></div><p className="fine">Locally edited audio, not AI-generated. Source licensing and any simulation status still apply; metadata is not carried into the exported clip.</p></div>:<div className="empty"><p>No clip rendered yet.</p><span>Import audio and select a range to preview the result.</span></div>}
 </Section></div>
}
