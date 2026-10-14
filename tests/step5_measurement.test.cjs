const {test}=require('node:test'),assert=require('node:assert/strict');
const {JSDOM}=require('jsdom');const {execFileSync}=require('node:child_process');
test('automatic pageview config receives explicit operator and site scope without second pageview',()=>{
 const html=execFileSync('python',['tests/render_analytics_fixture.py'],{encoding:'utf8'});
 for(const flag of ['0','1']){
  const dom=new JSDOM(html,{url:'https://stusaurus.github.io/daily-cost-jp/products/?test='+flag,runScripts:'dangerously',beforeParse(w){w.fetch=async()=>({ok:true,json:async()=>({products:[],page_count:1})});}});
  const configs=dom.window.dataLayer.filter(e=>e[0]==='config');assert.equal(configs.length,1);
  assert.equal(configs[0][2].operator_test,flag);assert.equal(configs[0][2].site_id,'daily-cost-jp');assert.equal(configs[0][2].traffic_environment,'production');
  assert(!dom.window.dataLayer.some(e=>e[0]==='event'&&e[1]==='page_view'));dom.window.close();
 }
});
test('development config is never classified as production',()=>{
 const html=execFileSync('python',['tests/render_analytics_fixture.py'],{encoding:'utf8'});
 const dom=new JSDOM(html,{url:'http://localhost/daily-cost-jp/products/?test=1',runScripts:'dangerously',beforeParse(w){w.fetch=async()=>({ok:true,json:async()=>({products:[],page_count:1})});}});
 const c=dom.window.dataLayer.find(e=>e[0]==='config');assert.equal(c[2].traffic_environment,'development');dom.window.close();
});
