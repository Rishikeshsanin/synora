import {validateJob,validateAsset,jobPath} from "./music.mjs";
import {validateSignedAsset,downloadPath} from "./media.mjs";
import {providerStatus} from "./provider.mjs";
import {libraryPath,parseLibraryPage} from "./library.mjs";
export type Form={prompt:string;mode:"instrumental"|"vocals";genres:string[];moods:string[];instruments:string[];duration:number;bpm:string;lyrics:string;language:string};
export type Spec={prompt:string;mode:"instrumental"|"vocals";genres:string[];moods:string[];instruments:string[];duration_seconds:number;bpm:number|null;lyrics:string|null;language:string|null};
export type Job={id:string;status:"queued"|"running"|"succeeded"|"failed"|"cancelled";progress:number;asset_id:string|null;error:{code:string;message:string}|null;created_at:string;updated_at:string;provider:string|null;simulated:boolean};
export type Asset={id:string;kind:"audio";mime_type:string;duration_seconds:number|null;url:string;expires_at:string|null;simulated:boolean};
export type LibraryItem={job:Job;asset:{id:string;duration_seconds:number}|null;prompt:string};
export type LibraryPage={items:LibraryItem[];next_cursor:string|null};
export const apiBase=(process.env.NEXT_PUBLIC_API_BASE_URL||"").replace(/\/$/,"");
async function request(path:string,token:string,signal:AbortSignal,options:RequestInit={}){
 if(!apiBase)throw new Error("API is not configured. Choose the local demo or configure the API.");
 if(!token)throw new Error("Sign in before creating or reading private tracks.");
 const response=await fetch(apiBase+path,{...options,signal,cache:"no-store",credentials:"omit",referrerPolicy:"no-referrer",redirect:"error",headers:{Authorization:"Bearer "+token,...options.headers}});
 const data=await response.json().catch(()=>null);
 if(!response.ok)throw new Error(typeof data?.message==="string"?data.message:"Request failed ("+response.status+").");
 return data;
}
export async function submit(spec:Spec,key:string,token:string,signal:AbortSignal):Promise<Job>{return validateJob(await request("/v1/music/jobs",token,signal,{method:"POST",headers:{"Content-Type":"application/json","Idempotency-Key":key},body:JSON.stringify(spec)}))}
export async function readJob(id:string,token:string,signal:AbortSignal,simulated?:boolean):Promise<Job>{return validateJob(await request(jobPath(id),token,signal),id,simulated)}
export async function cancelJob(id:string,simulated:boolean,token:string,signal:AbortSignal):Promise<Job>{return validateJob(await request(jobPath(id,true),token,signal,{method:"POST"}),id,simulated)}
export async function readAsset(id:string,simulated:boolean,token:string,signal:AbortSignal,download=false):Promise<Asset>{return validateSignedAsset(validateAsset(await request(download?downloadPath(id):"/v1/assets/"+encodeURIComponent(id),token,signal),simulated),id)}
export async function readLibrary(token:string,signal:AbortSignal,cursor:string|null=null):Promise<LibraryPage>{return parseLibraryPage(await request(libraryPath(cursor),token,signal),cursor)}
export async function readCapabilities(signal:AbortSignal):Promise<ReturnType<typeof providerStatus>>{if(!apiBase)throw new Error("API not configured.");const res=await fetch(apiBase+"/v1/music/capabilities",{signal,cache:"no-store",credentials:"omit",redirect:"error",referrerPolicy:"no-referrer"});if(!res.ok)throw new Error("Capabilities unavailable.");return providerStatus(await res.json())}
export function demoAudio():string{
 const rate=16000,n=rate*15,buf=new ArrayBuffer(44+n*2),v=new DataView(buf);
 const str=(offset:number,s:string)=>{for(let i=0;i<s.length;i++)v.setUint8(offset+i,s.charCodeAt(i))};
 str(0,"RIFF");v.setUint32(4,36+n*2,true);str(8,"WAVE");str(12,"fmt ");v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,rate,true);v.setUint32(28,rate*2,true);v.setUint16(32,2,true);v.setUint16(34,16,true);str(36,"data");v.setUint32(40,n*2,true);
 const notes=[220,261.626,329.628,293.665,196,246.942,293.665,261.626];
 for(let i=0;i<n;i++){const t=i/rate,beat=t%0.75,f=notes[Math.floor(t/0.75)%notes.length],env=Math.min(1,beat/0.045)*Math.exp(-beat*4)*Math.min(1,(15-t)/0.4);v.setInt16(44+2*i,Math.round(6500*env*(Math.sin(2*Math.PI*f*t)+0.25*Math.sin(4*Math.PI*f*t))),true)}
 return URL.createObjectURL(new Blob([buf],{type:"audio/wav"}));
}
