// Actual isolated Core/files/terminal; no native chooser or external installer.
const {browserQA}=require('./ux6_browser_support.cjs');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
async function main(){
 const output=path.resolve(process.argv[2]||'.codex-local/ux-6/after/integrations');await fs.mkdir(output,{recursive:true});
 const qa=await browserQA(),{api,handshake}=qa,checks=[];
 const root=path.resolve(handshake.workbench.root);assert.ok(path.basename(path.dirname(root)).startsWith('smarti-unittest-'));
 const call=async(method,route,body)=>{const r=await api(method,route,body);assert.ok(r.status>=200&&r.status<300,`${route}: ${r.status}`);return r.body.data;};
 const check=(name,ok)=>{assert.ok(ok,name);checks.push(name);};
 try{
  const custom=path.join(root,'ux6_echo.py');await fs.writeFile(custom,'def main():\n    return {"result": "UX6 local fixture"}\n');
  let tools=await call('POST','/v2/management/tools',{action:'install_custom',path:custom});
  check('real local custom install writes trusted catalog item',tools.extensions.some(e=>e.name==='ux6_echo'&&e.kind==='custom'&&e.trust==='trusted'));
  tools=await call('POST','/v2/management/tools',{action:'set_trust',kind:'custom',name:'ux6_echo',trusted:false});check('revoking custom trust disables execution',tools.extensions.some(e=>e.name==='ux6_echo'&&!e.enabled));
  const skill=path.join(root,'ux6_local_skill');await fs.mkdir(skill);await fs.writeFile(path.join(skill,'SKILL.md'),'---\nname: ux6_local_skill\ndescription: Isolated acceptance fixture\n---\nRead the supplied QA text. No external installs.\n');
  tools=await call('POST','/v2/management/tools',{action:'install_skill',path:skill});check('real local skill install preserves trust and source',tools.extensions.some(e=>e.name==='ux6_local_skill'&&e.kind==='skill'&&e.source==='local'));
  for(const [kind,name] of [['custom','ux6_echo'],['skill','ux6_local_skill']]){tools=await call('POST','/v2/management/tools',{action:'delete',kind,name});check(`${kind} removal updates actual catalog`,!tools.extensions.some(e=>e.kind===kind&&e.name===name));}
  const unpinned=await api('POST','/v2/management/tools',{action:'install_mcp',package:'ux6-unpinned'});check('unpinned MCP blocked before package execution',unpinned.status===400);
  const preview=await call('GET','/v2/workbench/file?path=reading.pdf');check('real PDF preview returns the original PDF bytes',preview.kind==='pdf'&&Buffer.from(preview.data_url.split(',')[1],'base64').subarray(0,8).toString().startsWith('%PDF-1.4'));
  const terminal=await call('POST','/v2/workbench/terminals',{});
  await call('POST',`/v2/workbench/terminals/${terminal.id}`,{action:'write',text:"Start-Sleep -Seconds 2; Write-Output 'UX6_BACKGROUND_DONE'"});
  let outputText='',deadline=Date.now()+15000;
  while(Date.now()<deadline&&!outputText.includes('UX6_BACKGROUND_DONE')){await new Promise(r=>setTimeout(r,150));outputText+=(await call('GET',`/v2/workbench/terminals/${terminal.id}`)).output;}
  check('actual terminal continues without a mounted renderer',outputText.includes('UX6_BACKGROUND_DONE'));
  await call('DELETE',`/v2/workbench/terminals/${terminal.id}`,{});
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({checks,scope:'real Core persistence/local installs/trust/terminal/PDF; MCP rejection only; no live external MCP, OS picker, Office GUI or account'},null,2));
 }catch(e){await fs.writeFile(path.join(output,'failure.json'),JSON.stringify({error:String(e),checks},null,2));throw e;}finally{await qa.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
