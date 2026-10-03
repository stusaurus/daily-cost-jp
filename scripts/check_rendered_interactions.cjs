/* Exercise generated feature scripts without a browser or external API calls. */
const {JSDOM,VirtualConsole}=require('jsdom');
const fs=require('node:fs');
const path=require('node:path');
const catalog=JSON.parse(fs.readFileSync('site/assets/comparison-catalog.json','utf8'));
(async()=>{
 for(const file of ['index.html','categories/tissue/index.html','today/index.html']){
  const errors=[];const console=new VirtualConsole();console.on('jsdomError',e=>errors.push(e.message));
  const dom=new JSDOM(fs.readFileSync(path.join('site',file),'utf8'),{
   url:'https://stusaurus.github.io/daily-cost-jp/'+file.replace('index.html',''),runScripts:'dangerously',virtualConsole:console,
   beforeParse(w){w.fetch=async()=>({ok:true,json:async()=>catalog});w.matchMedia=()=>({matches:true,addEventListener(){}});w.HTMLElement.prototype.scrollIntoView=function(){};}
  });
  dom.window.eval(fs.readFileSync('site/assets/purchase-tools.js','utf8'));
  await new Promise(r=>setImmediate(r));
  const d=dom.window.document;
  if(errors.length)throw Error(file+': '+errors.join('; '));
  const compare=d.querySelectorAll('[data-product-tool="compare"]');
  if(compare.length<2)throw Error(file+': comparison controls missing');
  compare[0].click();compare[1].click();d.getElementById('show-comparison').click();
  if(d.getElementById('purchase-tool-panel').hidden)throw Error(file+': comparison did not open');
  if(d.querySelector('#purchase-tool-panel a').dataset.conversionSource!=='comparison')throw Error(file+': comparison attribution lost');
  d.querySelector('[data-product-tool="save"]').click();d.getElementById('show-saved').click();
  if(d.querySelector('#purchase-tool-panel a').dataset.conversionSource!=='saved')throw Error(file+': saved attribution lost');
  dom.window.close();process.stdout.write('Generated scripts and save/compare passed: '+file+'\n');
 }
})().catch(e=>{process.stderr.write(e.stack+'\n');process.exitCode=1;});
