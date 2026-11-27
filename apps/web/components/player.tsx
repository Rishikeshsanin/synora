"use client";
import {useEffect,useRef,useState} from "react";
import WaveSurfer from "wavesurfer.js";
import type {Asset} from "../lib/api";
export default function Player({asset,onRefresh}:{asset:Asset;onRefresh:()=>Promise<Asset>}){
 const waveform=useRef<HTMLDivElement>(null),audio=useRef<HTMLAudioElement>(null);
 const [warning,setWarning]=useState(""),[busy,setBusy]=useState(false);
 useEffect(()=>{if(!waveform.current||!audio.current)return;setWarning("");const ws=WaveSurfer.create({container:waveform.current,media:audio.current,waveColor:"#777e79",progressColor:"#8cae85",height:72,barWidth:2,barGap:3,barRadius:2,interact:true});ws.on("error",()=>setWarning("Waveform unavailable. Try refreshing the audio link."));void ws.load(asset.url).catch(()=>setWarning("Waveform unavailable. Native playback may still work."));return()=>ws.destroy()},[asset.url]);
 async function download(){setBusy(true);setWarning("");try{const fresh=await onRefresh();const res=await fetch(fresh.url);if(!res.ok)throw new Error("Download unavailable.");const blob=await res.blob();const url=URL.createObjectURL(blob);const a=document.createElement("a");a.href=url;a.download="synora-"+fresh.id+"."+(fresh.mime_type.includes("mpeg")?"mp3":fresh.mime_type.includes("wav")?"wav":fresh.mime_type.includes("ogg")?"ogg":fresh.mime_type.includes("flac")?"flac":"audio");a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(e){setWarning(e instanceof Error?e.message:"Download failed.")}finally{setBusy(false)}}
 return <div className="player"><div ref={waveform} aria-hidden="true"/><audio ref={audio} controls preload="metadata" src={asset.url} onError={()=>setWarning("Audio link could not be played. Refresh and try again.")} aria-label="Track playback"/>{warning&&<p role="status" className="notice">{warning}</p>}<div className="row-actions"><button className="button secondary" disabled={busy} onClick={download}>{busy?"Downloading…":"Download audio"}</button>{!asset.url.startsWith("blob:")&&<button className="button secondary" onClick={()=>{void onRefresh().catch(e=>setWarning(String(e)))}}>Refresh link</button>}</div></div>
}
