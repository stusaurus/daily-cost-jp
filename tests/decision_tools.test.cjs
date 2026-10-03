const {test}=require('node:test');
const assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const {JSDOM}=require('jsdom');
const markup=execFileSync('python',['-c',`import sys
sys.path.insert(0,'scripts')
from build_site_decision import decision_markup
rows=[dict(id=cid,name=cid,emoji='',input_unit='箱' if cid=='tissue' else 'ロール' if cid=='toilet-paper' else 'g',placeholder='',metric_label='1箱' if cid=='tissue' else '1ロール' if cid=='toilet-paper' else '100g',factor=100 if cid=='laundry' else 1,best=40,median=60) for cid in ('tissue','toilet-paper','laundry')]
print(decision_markup(rows))`],{encoding:'utf8'});
for(const cid of ['tissue','toilet-paper'])test(`${cid}: a low box/roll price cannot produce a buy verdict or annual savings`,()=>{
 const dom=new JSDOM(markup,{url:'https://stusaurus.github.io/daily-cost-jp/',runScripts:'dangerously'});
 const d=dom.window.document;d.getElementById('judge-category').value=cid;
 d.getElementById('judge-price').value=100;d.getElementById('judge-quantity').value=10;d.getElementById('judge-monthly').value=100;
 d.getElementById('judge-button').click();
 const result=d.getElementById('judge-result');
 assert.match(result.textContent,/¥10.0/);assert.match(result.textContent,/未確認/);
 assert.doesNotMatch(result.textContent,/かなり買い|年間約/);
 assert.equal(result.querySelector('a').getAttribute('href'),`/daily-cost-jp/categories/${cid}/`);dom.window.close();
});
test('laundry retains mass-based calculation and candidate benchmark',()=>{
 const dom=new JSDOM(markup,{runScripts:'dangerously'});const d=dom.window.document;
 d.getElementById('judge-category').value='laundry';d.getElementById('judge-price').value=100;d.getElementById('judge-quantity').value=1000;
 d.getElementById('judge-button').click();assert.match(d.getElementById('judge-result').textContent,/かなり買い/);assert.match(d.getElementById('judge-result').textContent,/100g/);dom.window.close();
});
