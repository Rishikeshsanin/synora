"use client";
import {useEffect,useRef,useState,useCallback} from "react";
import WaveSurfer from "wavesurfer.js";
import {needsRefresh} from "../lib/media.mjs";
import type {Asset} from "../lib/api";
export default function Player({asset,onRefresh}:{asset:Asset;onRefresh:(download?:boolean)=>Promise<Asset>}){
 const waveform=useRef<HTMLDivElement>(null),audio=useRef<HTMLAudioElement>(null);
 const [warning,setWarning]=useState(""),[busy,setBusy]=useState(false);
 const refreshing=useRef(false),autoTried=useRef(false),restore=useRef<{time:number;play:boolean}|null>(null);
 const refreshRef=useRef(onRefresh);
 useEffect(()=>{refreshRef.current=onRefresh},[onRefresh]);
 const recover=useCallback(async (automatic=false,play=false)=>{
   if(asset.url.startsWith("blob:")||refreshing.current||(automatic&&autoTried.current))return;
   refreshing.current=true;autoTried.current=true;setWarning("");
   const el=audio.current;restore.current={time:el?.currentTime||0,play:play||Boolean(el&&!el.paused)};
   try{const fresh=await refreshRef.current(false);if(fresh.url===asset.url){restore.current=null;setWarning("Audio link could not be refreshed. Try again later.")}}
   catch{restore.current=null;setWarning("Could not refresh private audio. Check your session and retry.")}
   finally{refreshing.current=false}
 },[asset.url]);
 useEffect(()=>{
   if(!waveform.current||!audio.current)return;
   if(needsRefresh(asset)){void recover(true);return}
   let mounted=true;
   const ws=WaveSurfer.create({container:waveform.current,media:audio.current,waveColor:"#777e79",progressColor:"#8cae85",height:72,barWidth:2,barGap:3,barRadius:2,interact:true,fetchParams:{credentials:"omit",referrerPolicy:"no-referrer",cache:"no-store"}});
   const fail=()=>{if(mounted)setWarning("Waveform unavailable. Native playback may still work.")};
   ws.on("error",fail);void ws.load(asset.url).catch(fail);
   return()=>{mounted=false;ws.destroy()};
 },[asset,recover]);
 async function download(){setBusy(true);setWarning("");try{
   let fresh=await refreshRef.current(true);
   const get=()=>fetch(fresh.url,{credentials:"omit",cache:"no-store",referrerPolicy:"no-referrer",signal:AbortSignal.timeout(30000)});
   let res=await get();if(!fresh.url.startsWith("blob:")&&(res.status===401||res.status===403)){fresh=await refreshRef.current(true);res=await get()}
   if(!res.ok)throw new Error("Download unavailable.");
   const blob=await res.blob();if(!blob.size)throw new Error("Empty audio download.");
   const url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download="synora-"+fresh.id+"."+(fresh.mime_type.includes("mpeg")?"mp3":fresh.mime_type.includes("wav")?"wav":fresh.mime_type.includes("ogg")?"ogg":fresh.mime_type.includes("flac")?"flac":"audio");a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
 }catch{setWarning("Download failed. Check your connection and retry.")}finally{setBusy(false)}}
 return <div className="player"><div ref={waveform} aria-hidden="true"/><audio ref={audio} controls preload="metadata" src={asset.url} onLoadedMetadata={()=>{const el=audio.current,saved=restore.current;if(!el)return;autoTried.current=false;if(saved){restore.current=null;el.currentTime=Math.min(saved.time,Number.isFinite(el.duration)?el.duration:saved.time);if(saved.play)void el.play().catch(()=>setWarning("Press play to resume audio."))}}} onPlay={()=>{if(needsRefresh(asset)){audio.current?.pause();void recover(true,true)}}} onError={()=>{setWarning("Audio link could not be played. Refresh and try again.");void recover(true)}} aria-label="Track playback"/>{warning&&<p role="status" className="notice">{warning}</p>}<div className="row-actions"><button className="button secondary" disabled={busy} onClick={download}>{busy?"Downloading…":"Download audio"}</button>{!asset.url.startsWith("blob:")&&<button className="button secondary" onClick={()=>void recover()}>Refresh link</button>}</div></div>
}
