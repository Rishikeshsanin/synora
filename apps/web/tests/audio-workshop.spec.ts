import {test,expect} from "@playwright/test";
import {readFile} from "node:fs/promises";
function fixture(){
 const size=16000,b=Buffer.alloc(44+size);b.write("RIFF");b.writeUInt32LE(36+size,4);b.write("WAVEfmt ",8);b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(8000,24);b.writeUInt32LE(16000,28);b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write("data",36);b.writeUInt32LE(size,40);for(let i=44;i<b.length;i+=2)b.writeInt16LE(10000,i);return b
}
test("local WAV clip renders, plays and downloads exact trimmed frames",async({page},testInfo)=>{
 await page.setViewportSize({width:390,height:844});await page.goto("/studio");await page.getByRole("button",{name:"Audio Workshop"}).click();
 await page.getByLabel("Import PCM WAV").setInputFiles({name:"fixture.wav",mimeType:"audio/wav",buffer:fixture()});
 await expect(page.getByRole("button",{name:"Render local clip"})).toBeDisabled();
 await page.getByLabel("I own or have permission to edit this audio.").check();
 await page.getByLabel("Clip start (seconds)").fill("0.25");await page.getByLabel("Clip end (seconds)").fill("0.75");
 await page.getByLabel("Fade in (seconds)").fill("0.1");await page.getByLabel("Fade out (seconds)").fill("0.1");
 await page.getByRole("button",{name:"Render local clip"}).click();
 const audio=page.getByLabel("Clip playback");await expect.poll(()=>audio.evaluate(el=>(el as HTMLAudioElement).duration)).toBeCloseTo(0.5,2);
 await audio.evaluate(el=>(el as HTMLAudioElement).play());await expect.poll(()=>audio.evaluate(el=>(el as HTMLAudioElement).currentTime)).toBeGreaterThan(0);
 const event=page.waitForEvent("download");await page.getByRole("link",{name:"Download WAV clip"}).click();const download=await event;expect(await download.failure()).toBeNull();const path=await download.path();expect(path).toBeTruthy();const bytes=await readFile(path!);expect(bytes.toString("ascii",0,4)).toBe("RIFF");expect(bytes.readUInt32LE(40)).toBe(8000);expect(bytes.readInt16LE(44)).toBe(0);expect(bytes.readInt16LE(44+4000)).toBe(10000);expect(bytes.readInt16LE(bytes.length-2)).toBe(0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:testInfo.outputPath("audio-workshop-mobile.png"),fullPage:true});
 await page.getByLabel("Clip start (seconds)").fill("0.9");await expect(page.getByRole("link",{name:"Download WAV clip"})).toHaveCount(0);await page.getByRole("button",{name:"Render local clip"}).click();await expect(page.getByRole("main").getByRole("alert")).toContainText("valid clip range");
 await page.getByRole("button",{name:"Music Studio"}).click();await page.getByRole("button",{name:"Audio Workshop"}).click();await expect(page.getByRole("button",{name:"Render local clip"})).toHaveCount(0);
});
test("rejects corrupt audio without exposing playback",async({page})=>{
 await page.goto("/studio");await page.getByRole("button",{name:"Audio Workshop"}).click();
 await page.getByLabel("Import PCM WAV").setInputFiles({name:"invalid.wav",mimeType:"audio/wav",buffer:Buffer.alloc(64)});
 await expect(page.getByRole("main").getByRole("alert")).toContainText("Invalid or truncated");
 await expect(page.getByLabel("Clip playback")).toHaveCount(0);
});
