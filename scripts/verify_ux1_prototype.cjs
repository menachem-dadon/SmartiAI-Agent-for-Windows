// Full isolated UX-1 QA. Real product renderers; synthetic Core/native bridge.
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const base = process.argv[2] || "http://127.0.0.1:1432";
const output = path.resolve(process.argv[3] || ".codex-local/ux-1/qa/full");
const sections = ["settings_ai","settings_security","settings_tools","settings_appearance","settings_advanced","workspace","usage","tools","memory","tasks","diagnostics","logs","about"];
async function run() {
 await fs.mkdir(output,{recursive:true});
 const browser = await chromium.launch({channel:"msedge",headless:true});
 const context = await browser.newContext({viewport:{width:1380,height:900},acceptDownloads:true});
 const page = await context.newPage();
 const errors=[], remote=[], checks=[], layouts=[], coverage=[];
 page.on("pageerror",e=>errors.push(e.message));
 context.on("request",r=>{if(!r.url().startsWith(base)&&!r.url().startsWith("data:")&&!r.url().startsWith("blob:")) remote.push(r.url());});
 await context.route("**/*",r=>r.request().url().startsWith(base)||r.request().url().startsWith("data:")?r.continue():r.abort());
 const check=(name,condition)=>{assert.ok(condition,name);checks.push(name);};
 const button=(name,root=page)=>root.getByRole("button",{name,exact:true});
 const nav=async id=>{await page.locator(`nav button[data-section="${id}"]`).click();await page.waitForTimeout(id==="memory"?350:100);};
 const theme=async value=>{if(await page.locator(".ux-prototype").getAttribute("data-theme")!==value)await button(value==="dark"?"מעבר למצב כהה":"מעבר למצב בהיר").click();};
 const tab=async name=>{
   if(name==="קנבס" && await page.getByRole("tab",{name,exact:true}).count()===0) {
     await button("סגירת סביבת העבודה").click();
     await page.locator(".canvas-open-card button").last().click();return;
   }
   const existing=page.getByRole("tab",{name,exact:true}).first();
   if(await existing.count()===0) {await button("הוספת לשונית סביבת עבודה").click();await page.getByRole("menuitem",{name,exact:true}).click();}
   else await existing.click();
 };
 const finish=async()=>{await fs.writeFile(path.join(output,"report.json"),JSON.stringify({checks,layouts,coverage,errors,remote,trace:await page.evaluate(()=>window.__UX1_DEMO__?.trace)},null,2));};
 try {
 await page.goto(`${base}/ux-1.html`,{waitUntil:"networkidle"});
 await page.getByRole("textbox",{name:"כתיבת הודעה",exact:true}).waitFor();
 await page.waitForTimeout(300);
 check("no initial overlay/toast",await page.locator(".ux-toast").count()===0&&await page.locator(".ux-notice").count()===0);
 check("bounded brand image",await page.locator(".ux-brand-logo").evaluate(x=>x.getBoundingClientRect().width===34&&x.getBoundingClientRect().height===34));
 check("sidebar owns no scroll",await page.locator(".ux-sidebar").evaluate(x=>getComputedStyle(x).overflow==="hidden"));
 const process=page.locator(".ux-message .agent-process").last();
 check("single completed process",await page.locator(".agent-process:visible").count()===1);
 check("single result card",await page.locator(".canvas-open-card:visible").count()===1&&await page.locator(".ux-artifact-card").count()===0);
 await process.locator(":scope >summary").click();
 const group=process.locator(".agent-tool-group").first();await group.locator(":scope >summary").click();
 const tool=group.locator(".agent-tool-row").first();await tool.locator(":scope >summary").click();
 check("three-level process hierarchy",await tool.getAttribute("open")!==null&&await group.getAttribute("open")!==null&&await process.getAttribute("open")!==null);
 check("real report/input/output contract",(await tool.innerText()).includes("קלט ופרמטרי הפעלה")&&(await tool.innerText()).includes("פלט הכלי")&&(await tool.innerText()).includes("meetings,1200")&&(await process.innerText()).includes("אבדוק את מסמך"));
 await page.screenshot({path:path.join(output,"light-process.png")});
 await process.locator(":scope >summary").click();
 const downloadPromise=page.waitForEvent("download");await button("הורד קובץ").last().click();const download=await downloadPromise;check("Python code download",download.suggestedFilename().endsWith(".py"));await download.saveAs(path.join(output,"downloaded-demo.py"));check("downloaded source content",(await fs.readFile(path.join(output,"downloaded-demo.py"),"utf8")).includes('print(summary["next_step"])'));
 await button("פתיחת סביבת העבודה").click();
 check("empty workspace launcher initially",await page.locator('.ux-workbench-tabs [role="tab"]').count()===0&&await page.locator('.ux-workbench-launch-grid button').count()===4&&await page.locator('.ux-document-pane').count()===0);
 check("one workbench toolbar",await page.locator(".ux-workbench-bar").count()===1&&await page.locator(".ux-workbench-controls,.ux-artifact-mode,.ux-artifact-toolbar").count()===0);
 check("one workspace close",await button("סגירת סביבת העבודה").count()===1);
 check("guide hides in workbench",await page.locator(".ux-try-guide").count()===0);
 await page.screenshot({path:path.join(output,"light-workbench-clean.png")});
 await page.locator('.ux-workbench-launch-grid button').filter({hasText:'תוצרים'}).click();
 await button("הרחבת סביבת העבודה").click();check("expanded workbench",await page.locator('.ux-work-area').getAttribute('data-single')==='true');
 await button("כיווץ סביבת העבודה").click();
 check("artifact list accessible",await page.locator(".artifacts-panel").isVisible());
 await button("פתיחת מסמך").click();
 await button("עריכת מסמך").click();await page.getByRole("textbox",{name:"עריכת מסמך",exact:true}).fill("# UX1 retained edit");await button("שמירה").click();await page.getByText("השמירה נכשלה. הטקסט",{exact:false}).waitFor();check("failed save retains text",await page.getByRole("textbox",{name:"עריכת מסמך",exact:true}).inputValue()==="# UX1 retained edit");
 await button("אפשר ניסיון מוצלח").click();await button("שמירה").click();await page.waitForTimeout(700);check("successful save clears pending state",await page.locator(".ux-artifact-footer button").isEnabled()&&!((await page.locator(".ux-artifact-footer").innerText()).includes("נכשלה")));await button("קריאת מסמך").click();
 check("no guessed settings icon on reading mode",await page.locator('.ux-document-bar [data-icon="settings"]').count()===0);
 await page.locator(".ux-document-actions summary").click();const docDownload=page.waitForEvent("download");await button("הורדת מסמך").click();const downloadedDoc=await docDownload;check("document download from contextual menu",downloadedDoc.suggestedFilename().endsWith(".md"));await page.locator(".ux-document-actions summary").press("Escape");
 check("document action menu closes after download",await page.locator(".ux-document-actions").getAttribute("open")===null);
 check("clean reading has no save toolbar",await page.locator(".ux-artifact-footer").count()===0);
 for(const name of ["קבצים","מסוף","קנבס","דפדפן"]) {
   await tab(name);await page.waitForTimeout(400);
   if(name==="קבצים") {await page.locator(".file-tree button").filter({hasText:"budget_2027.csv"}).click();check("source file preview",(await page.locator(".file-preview:visible").innerText()).includes("meetings,1200"));}
   if(name==="מסוף") {await page.getByRole("textbox",{name:"פקודת PowerShell"}).fill("echo UX1-demo");await page.getByRole("textbox",{name:"פקודת PowerShell"}).press("Enter");check("source terminal command path",(await page.locator(".terminal-panel:visible pre").innerText()).includes("UX1-demo"));}
   if(name==="קנבס") {check("source canvas iframe",await page.locator(".canvas-panel:visible iframe").count()===1);await page.frameLocator(".canvas-panel:visible iframe").getByRole("button",{name:"תכנן את המפגש הבא"}).click();check("canvas confirmation",await page.locator(".canvas-action-confirm").count()>0||await page.getByText("פעולה מהקנבס",{exact:false}).count()>0);}
   if(name==="דפדפן") {await button("תפריט דפדפן").click();await page.locator(".ux-native-menu").waitFor();check("source browser menu",(await page.locator(".ux-native-menu").innerText()).includes("היסטוריה"));await page.screenshot({path:path.join(output,"browser-menu.png")});await page.locator(".ux-native-menu button").first().click();}
 }
 await button("סגירת סביבת העבודה").click();
 check("chat restores after all workbench tabs",await page.locator(".ux-chat").isVisible());
 await button("הגדרות וספקים").first().click();
 check("management owns independent navigation",await page.locator(".ux-sidebar").isHidden()&&await page.locator('.ux-shell').getAttribute('data-page')==='settings');
 check("settings lead management navigation",(await page.locator('nav[aria-label="ניהול והגדרות"] button').first().getAttribute('data-section'))==='settings_ai');
 await page.getByRole("checkbox",{name:"הצג הגדרות מתקדמות",exact:true}).check();
 await page.waitForTimeout(200); // Measure the resting thumb after its 160 ms transition.
 const advancedThumb=await page.locator('.source-advanced-pill .source-switch>span').evaluate(x=>{const c=getComputedStyle(x,'::after');return {right:parseFloat(c.right),width:parseFloat(c.width),shift:new DOMMatrixReadOnly(c.transform).m41,track:x.clientWidth};});
 check("RTL enabled switch thumb on physical left",advancedThumb.track-advancedThumb.right-advancedThumb.width+advancedThumb.shift<advancedThumb.track/2-advancedThumb.width/2);
 for(const value of ["light","dark"]) {
   await theme(value);
   for(const width of [360,900,1380]) {
     await page.setViewportSize({width,height:653});
     for(const id of sections) {
       await nav(id);
       const sample=await page.locator(".ux-management-body").evaluate(x=>({w:x.clientWidth,scroll:x.scrollWidth,page:document.documentElement.scrollWidth,view:innerWidth}));
       layouts.push({theme:value,width,section:id,...sample});
       check(`management width ${value}/${width}/${id}`,sample.scroll<=sample.w+1&&sample.page<=sample.view+1);
       check(`one management page heading ${value}/${width}/${id}`,await page.locator('.ux-management-body .ux-page-heading h1:visible').count()===1&&await page.locator('.management-hero h2:visible').count()===0);
       const sourceArtwork=await page.locator(".legacy-icon").evaluateAll(xs=>xs.every(x=>x.dataset.uxIcon&&x.src.includes("/src/ux1/icons/")));check(`new source artwork ${value}/${width}/${id}`,sourceArtwork);
       const broken=await page.locator("img").evaluateAll(xs=>xs.filter(x=>x.getClientRects().length&&(!x.complete||x.naturalWidth===0)).map(x=>x.src));check(`raster assets ${value}/${width}/${id}`,broken.length===0);
       if(value==="light"&&width===1380){coverage.push({section:id,settingPaths:await page.locator("[data-setting-path]").evaluateAll(xs=>xs.map(x=>x.dataset.settingPath))});await page.screenshot({path:path.join(output,`${id}.png`)});}
     }
   }
 }
 await page.setViewportSize({width:1380,height:900});await theme("light");await nav("settings_ai");
 check("settings grouped as real controls",await page.locator('.ux-settings-group').count()>0&&await page.locator('.ux-provider-group [data-setting-path="api_mode"] select').count()===1);
 check("no settings group jump; provider content preserved",await page.getByRole('combobox',{name:'קפיצה לקבוצת הגדרות'}).count()===0&&await page.locator('#ux-provider-group').count()===1);
 await page.locator('.ux-management-body').evaluate(x=>x.scrollTop=0);
 // Every provider workflow uses the source selector and source validation UI.
 const provider=page.locator('[data-setting-path="api_mode"] select');
 for(const id of ["gemini","openai","openai_codex_signin","anthropic","openrouter","groq","nvidia","cerebras","huggingface","deepseek","qwen","zhipu","moonshot","mistral","together","perplexity","xai","local"]) {await provider.selectOption(id);await page.waitForTimeout(80);check(`provider workflow ${id}`,await provider.inputValue()===id);}
 await provider.selectOption("openai");
 const key=page.locator('[data-setting-path="provider_api_key"] input');await key.fill("bad-demo");await page.getByText("המפתח נדחה.",{exact:false}).waitFor();check("provider rejection preserves configured key",await page.evaluate(()=>window.__UX1_DEMO__.settings().secrets.openai_api_key.masked==="••••A1B2"));await key.fill("good-demo");await page.getByText("בדיקת המפתח הצליחה:",{exact:false}).waitFor();check("provider retry",await key.inputValue()==="");
 await nav("memory");await button("זיכרון חדש").click();let memoryDialog=page.getByRole("dialog",{name:"זיכרון חדש",exact:true});await memoryDialog.getByRole("textbox").first().fill("UX-1 memory created");await button("שמירה",memoryDialog).click();await page.getByText("UX-1 memory created",{exact:true}).waitFor();check("memory create",true);let memoryCard=page.locator(".management-cards article").filter({hasText:"UX-1 memory created"});await button("עריכה",memoryCard).click();memoryDialog=page.getByRole("dialog",{name:"עריכת זיכרון",exact:true});await memoryDialog.getByRole("textbox").first().fill("UX-1 memory edited");await button("שמירה",memoryDialog).click();await page.getByText("UX-1 memory edited",{exact:true}).waitFor();check("memory edit",true);
 await nav("tools");await page.getByRole("checkbox",{name:"כבה file_manager",exact:true}).click();await page.getByRole("checkbox",{name:"הפעל file_manager",exact:true}).waitFor();check("builtin availability toggle",true);await page.getByRole("checkbox",{name:"הפעל file_manager",exact:true}).click();await page.getByRole("checkbox",{name:"כבה file_manager",exact:true}).waitFor();check("builtin availability restore",true);
 await nav("logs");const logDownload=page.waitForEvent("download");await button("ייצוא").click();await logDownload;check("trace export",true);
 await nav("about");await button("תצוגת מסך ההסכמה").click();await page.locator(".legal-confirm input").check();await button("אני מסכים").click();check("source agreement explicit acceptance",await page.locator(".ux-legal-preview").count()===0);
 await nav("tasks");check("task creation progressively disclosed",await page.locator(".task-create").isHidden());await button("משימה חדשה").click();check("task creation focuses preserved form",await page.locator(".task-create textarea").evaluate(x=>x===document.activeElement));await page.locator(".task-create textarea").fill("UX-1 synthetic task");await button("יצירת משימה").click();check("source task creation",(await page.locator(".management-cards").innerText()).includes("UX-1 synthetic task"));
 await nav("diagnostics");await button("בדיקה מהירה").click();await page.getByText("הבדיקה הסתיימה.",{exact:false}).waitFor();check("diagnostic details and repair",await page.locator(".management-cards details").count()===4&&await button("חיבור ספק").count()===1);await button("חיבור ספק").click();await button("אישור מפורש").click();await page.waitForTimeout(150);check("diagnostic simulated repair",(await page.locator(".management-cards").innerText()).includes("החיבור זמין"));
 await nav("settings_advanced");check("advanced settings and SSL",await page.locator('[data-setting-path="ssl_trust_mode"]').count()>0);
 await nav("settings_ai");await page.getByPlaceholder("חפש הגדרה").fill("SSL");await page.waitForTimeout(200);check("source cross-section settings search",(await page.locator(".ux-management-body").innerText()).includes("SSL"));await page.getByPlaceholder("חפש הגדרה").fill("");
 await nav("settings_appearance");await page.screenshot({path:path.join(output,"appearance-final.png")});
 await button("חזרה לשיחה").click();
 await button("מדריך התנסות").click();check("redesign rationale and three entry points",await page.locator('.ux-guide-routes button').count()===4&&(await page.locator('.ux-guide-content').innerText()).includes('הפעילות מתקפלת בשלוש רמות'));await page.keyboard.press('Escape');
 // Global dialog focus and retained draft/run behavior.
 await button("מדריך התנסות").click();await page.keyboard.press("Escape");check("Escape returns focus",await button("מדריך התנסות").evaluate(x=>x===document.activeElement));
 await button("שיחה חדשה").first().click();await page.getByRole("textbox",{name:"כתיבת הודעה",exact:true}).fill("סכם את התוכנית");await page.getByRole("textbox",{name:"כתיבת הודעה",exact:true}).press("Enter");await button("אישור לפעולה הזו").waitFor();await page.getByRole("textbox",{name:"כתיבת הודעה",exact:true}).fill("טיוטה בזמן עבודה");await button("אישור לפעולה הזו").click();await page.waitForTimeout(5200);check("draft survives simulated run",await page.getByRole("textbox",{name:"כתיבת הודעה",exact:true}).inputValue()==="טיוטה בזמן עבודה");
 await button("צירוף קובץ").click();await page.locator(".ux-attachment-choice").click();
 for(const value of ["light","dark"]) {await theme(value);for(const width of [360,500,900,1290,1380,1920]) {for(const height of [653,900]) {await page.setViewportSize({width,height});const g=await page.evaluate(()=>{const c=document.querySelector('.ux-composer').getBoundingClientRect();let controls=[...document.querySelectorAll('.ux-composer-controls button')].filter(x=>x.getClientRects().length);return {overflow:document.documentElement.scrollWidth>innerWidth,contained:controls.every(x=>{let r=x.getBoundingClientRect();return r.left>=c.left-1&&r.right<=c.right+1&&r.top>=c.top-1&&r.bottom<=c.bottom+1}),hit:controls.every(x=>{let r=x.getBoundingClientRect();return x.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))})}});check(`composer geometry ${value}/${width}/${height}`,!g.overflow&&g.contained&&g.hit);layouts.push({theme:value,width,height,chat:g});}}
 }
 await page.getByRole("textbox",{name:"כתיבת הודעה",exact:true}).fill("");
 await button("פתיחת סביבת העבודה").click();
 for(const value of ["light","dark"]) {await theme(value);for(const width of [360,900,1380]) {await page.setViewportSize({width,height:653});for(const kind of ["תוצרים","קבצים","מסוף","קנבס","דפדפן"]) {
 await tab(kind);await page.waitForTimeout(140);
 const sample=await page.locator(".ux-artifact").evaluate(x=>({width:x.clientWidth,scroll:x.scrollWidth,root:document.documentElement.scrollWidth,view:innerWidth}));
 const closeReachable=await button("סגירת סביבת העבודה").evaluate(x=>{const r=x.getBoundingClientRect();return x.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))});
 check(`workbench ${value}/${width}/${kind}`,sample.scroll<=sample.width+1&&sample.root<=sample.view+1&&closeReachable);layouts.push({theme:value,width,workbench:kind,...sample});
 if(kind==="דפדפן"&&value==="light"&&width===360)await page.screenshot({path:path.join(output,"narrow-browser.png")});
 if(kind==="תוצרים"&&value==="dark"&&width===1380)await page.screenshot({path:path.join(output,"dark-workbench.png")});
 await button("סגירת סביבת העבודה").click();check(`close restores chat ${value}/${width}/${kind}`,await page.locator(".ux-chat").isVisible());await button("פתיחת סביבת העבודה").click();
 }}}
 await button("סגירת סביבת העבודה").click();
 await page.setViewportSize({width:1380,height:900});await theme("light");await button("תרחישי התנסות").click();await page.getByRole("combobox",{name:"כמות הודעות"}).selectOption("1000");await page.keyboard.press("Escape");check("1000-message source renderer",await page.locator(".ux-message").count()===1000);
 await page.screenshot({path:path.join(output,"final-light-chat.png")});
 await page.waitForTimeout(500);
 const sourceIcons=await page.locator(".legacy-icon").evaluateAll(xs=>xs.map(x=>({src:x.src,name:x.dataset.uxIcon})));
 check("all source icons use new artwork",sourceIcons.every(x=>x.name&&x.src.includes('/src/ux1/icons/')));
 check("no arbitrary PNG decoration on text options",await page.locator('[data-demo-icon]:not([data-raster-only]):not(.source-tool-name)').count()===0);
 check("no SVG icons",await page.locator(".ux-prototype svg").count()===0);
 check("no remote/API traffic",remote.length===0);
 check("no runtime errors",errors.length===0);
 check("no unimplemented bridge paths",await page.evaluate(()=>!window.__UX1_DEMO__.trace.some(x=>x.unsupported)));
 check("isolated bridge",await page.evaluate(()=>window.__UX1_DEMO__.isolated===true));
 await finish();console.log(JSON.stringify({checks:checks.length,layouts:layouts.length,coverage:coverage.map(x=>({section:x.section,fields:x.settingPaths.length})),output},null,2));
 } catch(e) {await page.screenshot({path:path.join(output,"failure.png")});await finish();throw e;} finally {await browser.close();}
}
run().catch(e=>{console.error(e);process.exitCode=1});
