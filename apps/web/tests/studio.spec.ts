import {test,expect} from "@playwright/test";
test("landing and studio responsive screenshots",async({page},testInfo)=>{
 for(const width of [320,390,768,1366]){
   await page.setViewportSize({width,height:900});await page.goto("/");
   await expect(page.getByRole("heading",{level:1})).toContainText("Every idea");
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
   await page.screenshot({path:testInfo.outputPath("landing-"+width+".png"),fullPage:true});
   await page.getByRole("link",{name:"Start creating"}).click();
   await expect(page.getByRole("heading",{name:"Music Studio"})).toBeVisible();
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
   await page.screenshot({path:testInfo.outputPath("studio-"+width+".png"),fullPage:true});
 }
});
test("studio form, fixture provenance, native playback and download",async({page},testInfo)=>{
 await page.goto("/studio");await expect(page.getByRole("button",{name:"Create music"})).toBeDisabled();
 await page.getByRole("checkbox",{name:"Explicit local demo"}).check();
 await page.getByRole("button",{name:"Purpose",exact:true}).click();
 await page.getByRole("button",{name:/Film & story/}).click();
 await expect(page.getByLabel("Describe your sound")).toHaveValue(/cinematic/);
 await page.getByRole("button",{name:"Advanced",exact:true}).click();
 await page.getByRole("button",{name:"With vocals"}).click();
 await page.getByLabel("Lyrics (optional)").fill("Original test lyrics");
 await page.getByLabel("Language").selectOption("Telugu");
 await page.getByLabel("Tempo (optional BPM)").fill("100");
 await page.getByRole("button",{name:"Play local fixture"}).click();
 await expect(page.getByText("Local fixture · Not AI-generated").first()).toBeVisible();
 const audio=page.locator("audio");
 await expect.poll(()=>audio.evaluate(el=>(el as HTMLAudioElement).duration)).toBeCloseTo(15,0);
 await audio.evaluate(el=>(el as HTMLAudioElement).play());
 await expect.poll(()=>audio.evaluate(el=>(el as HTMLAudioElement).currentTime)).toBeGreaterThan(0);
 const downloading=page.waitForEvent("download");await page.getByRole("button",{name:"Download audio"}).click();const download=await downloading;expect(download.suggestedFilename()).toMatch(/\.wav$/);expect(await download.failure()).toBeNull();
 await page.getByRole("button",{name:"Light mode"}).click();await expect(page.locator(".workspace")).toHaveAttribute("data-theme","light");
 await page.screenshot({path:testInfo.outputPath("fixture-light.png"),fullPage:true});
 await page.getByRole("button",{name:"Creative Library"}).click();await expect(page.getByRole("heading",{name:"Your tracks"})).toBeVisible();
});
test("keyboard focus, reduced motion and future studio",async({page})=>{
 await page.emulateMedia({reducedMotion:"reduce"});await page.goto("/studio");await page.keyboard.press("Tab");await expect(page.getByRole("link",{name:"Skip to content"})).toBeFocused();await page.keyboard.press("Enter");await expect(page).toHaveURL(/#main$/);await page.getByRole("button",{name:"Creative Studio"}).click();await expect(page.getByText(/Video generation is not available/)).toBeVisible();
});
