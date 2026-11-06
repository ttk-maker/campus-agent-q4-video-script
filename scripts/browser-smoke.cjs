const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.WEB_URL||'http://127.0.0.1:8770',out=process.env.BROWSER_OUTPUT||'examples/browser';fs.mkdirSync(out,{recursive:true});
(async()=>{const browser=await chromium.launch(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL,headless:true}:{headless:true});const page=await browser.newPage({viewport:{width:1440,height:1100}});const checks=[],errors=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text())});
 const ok=(name,v=true)=>{assert.ok(v,name);checks.push({name,passed:true});};
 async function done(){await page.waitForFunction(()=>!document.querySelector('#run').disabled,{},{timeout:30000});}
 async function run(name){await page.selectOption('#scenario',name);await page.click('#run');await done();}
 async function job(){const id=await page.evaluate(()=>localStorage.getItem('q4-job'));return(await page.request.get(base+'/api/jobs/'+id)).json();}
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#scenario').options.length>1);ok('bootstrap available');
 await run('normal');ok('normal complete',await page.textContent('#state')==='已完成');ok('duration actual28',await page.textContent('#duration')==='28s');ok('source and fact displayed',(await page.textContent('#scenes')).includes('P01 / F01'));
 await page.click('#resume');await done();ok('repeat zero model steps',(await job()).result.steps_used===0);
 const dlPromise=page.waitForEvent('download');await page.click('#download');const dl=await dlPromise;await dl.saveAs(path.join(out,'downloaded-run.json'));const downloaded=JSON.parse(fs.readFileSync(path.join(out,'downloaded-run.json'),'utf8'));ok('download includes true checks',downloaded.result.rules_check.passed&&downloaded.result.duration_check.passed);
 await run('over_duration');const over=await job();ok('38 reduced and rechecked',over.result.revision_history[0].duration_check.total_seconds===38&&over.result.estimated_total_seconds===28);
 await page.reload();await page.waitForFunction(()=>document.querySelector('#state').textContent==='已完成');ok('reload restores original scenario',await page.inputValue('#scenario')==='over_duration');
 await page.locator('#editor-panel').evaluate(n=>n.open=true);let script=JSON.parse(await page.inputValue('#editor'));script.scenes[0].voiceover='效率提升80%';await page.fill('#editor',JSON.stringify(script));ok('unsubmitted edit clearly marked',(await page.textContent('#edit-state')).includes('尚未检查'));
 await page.click('#review');await done();let edited=await job();ok('manual review not claimed as model',edited.result.mode==='review');ok('unsupported edited claim rejected',edited.result.status==='cannot_satisfy'&&edited.result.script_status==='unverified');ok('user text not silently repaired',edited.result.script.scenes[0].voiceover==='效率提升80%');
 await page.click('#resume');await done();ok('agent repairs then rechecks',(await job()).result.status==='completed'&&!(await page.textContent('#scenes')).includes('80%'));
 await page.locator('#editor-panel').evaluate(n=>n.open=true);script=JSON.parse(await page.inputValue('#editor'));script.scenes[0].seconds=50;await page.fill('#editor',JSON.stringify(script));await page.click('#review');await done();ok('edited duration invalidates ready',(await job()).result.estimated_total_seconds===50&&await page.textContent('#ready')==='未就绪');
 await run('missing');ok('missing key inputs',await page.textContent('#state')==='待补信息');
 await run('no_materials');ok('empty search no invented script',(await job()).result.script===null&&await page.textContent('#state')==='待补信息');
 await run('tool_failure');ok('tool failure visible',await page.textContent('#state')==='执行失败');await page.click('#resume');await done();ok('tool failure resume',await page.textContent('#state')==='已完成');
 await run('too_short');ok('impossible limit not success',await page.textContent('#state')==='无法满足');
 await run('rewrite');const rew=await job();ok('query rewrite affects tools',rew.trace[0].observation.status==='empty'&&rew.trace[1].observation.status==='found');
 await page.locator('#editor-panel').evaluate(n=>n.open=true);script=JSON.parse(await page.inputValue('#editor'));script.title='<img src=x onerror=alert(1)>';await page.fill('#editor',JSON.stringify(script));await page.click('#review');await done();ok('untrusted title rendered safely',await page.locator('#result img').count()===0&&(await page.textContent('#script-title')).includes('<img'));
 await page.fill('#editor','{broken');await page.click('#review');ok('invalid edit JSON actionable',(await page.textContent('#notice')).includes('JSON'));
 await run('over_duration');await page.locator('#editor-panel').evaluate(n=>n.open=false);await page.screenshot({path:path.join(out,'desktop.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});ok('mobile width fits',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:path.join(out,'mobile.png'),fullPage:true});
 await page.goto(base+'/manual.html');ok('manual available',(await page.textContent('h1')).includes('分镜'));ok('no browser errors',errors.length===0);
 fs.writeFileSync(path.join(out,'report.json'),JSON.stringify({timestamp:new Date().toISOString(),checks,errors,passed:true},null,2));await browser.close();console.log(`${checks.length} browser checks passed`);
})().catch(e=>{console.error(e);process.exit(1)});
