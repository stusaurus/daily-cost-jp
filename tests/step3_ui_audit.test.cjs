'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const s=require('../scripts/step3_ui_audit.cjs');
test('UI recipe is fixed, idempotent and never hides overflow',()=>{
 const css='.lab-masthead{}.lab-section-head{}';const changed=s.repair(css);
 assert.equal(changed,css+s.BLOCK);assert.equal(s.repair(changed),null);assert.equal(s.repair('body{}'),null);
 assert.equal(s.repair(css+'.home-rank-all{height:20px}'),null);
 assert.doesNotMatch(s.BLOCK,/overflow|color|font|url|display:none/);
});
test('geometry, text, name and contrast detectors retain uncertainty',()=>{
 const issues=s.assess({width:320,documentWidth:350,overflow:[{selector:'#wide'}],controls:[{selector:s.TARGET,width:150,height:16,recipeTarget:true,name:'Ranking'},{selector:'#button',width:50,height:44,name:''}],text:[{selector:'#text',clipped:true,intentionalClamp:false,height:10,scrollHeight:20,contrast:2,requiredContrast:4.5},{selector:'#clamp',clipped:true,intentionalClamp:true,contrast:null}],overlaps:[{selector:'#overlap',occluder:'#cover'}]});
 assert.deepEqual(issues.map(e=>e.code),['HORIZONTAL_OVERFLOW','HOME_RANKING_TAP_TARGET','ACCESSIBLE_NAME_MISSING','TEXT_CLIPPING_REVIEW','CONTRAST_REVIEW','TEXT_OVERLAP_REVIEW']);
 assert.equal(s.contrast([0,0,0],[255,255,255]),21);
});
test('UI proof rejects incomplete matrices and source/destination/appearance changes',()=>{
 const css='.lab-masthead{}.lab-section-head{}',candidate=s.repair(css);
 const before=s.PAGES.flatMap(p=>s.WIDTHS.map(w=>({path:p,viewport:w,status:'PASS',css_hash:s.sha(css),protected_hash:'same',dom:{documentWidth:w},issues:[],target:p==='/'?{count:1,href:'trends/',rect:{width:180,height:16},color:'black',font:'14px serif'}:null})));
 const after=structuredClone(before);for(const r of after)if(r.target)r.target.rect.height=44;
 assert.equal(s.compare(before,after,css,candidate).length,18);
 const check=mutation=>{const a=structuredClone(after);mutation(a);assert.throws(()=>s.compare(before,a,css,candidate));};
 check(a=>a[0].protected_hash='changed');check(a=>a[0].target.href='https://evil.test');check(a=>a[0].target.color='red');check(a=>a[0].target.rect.height=43);check(a=>a[1].dom.documentWidth=500);check(a=>a[2].issues.push({code:'SCRIPT',selector:'#new'}));check(a=>a[3].status='UNAVAILABLE');
 assert.throws(()=>s.compare(before.slice(1),after,css,candidate));
});


test('manual heading recipe is exact, narrow, non-idempotent, and does not permit unrelated CSS',()=>{
 const oldDesktop='.art-page-header{position:relative;padding-right:max(260px,calc((100vw - 1180px)/2 + 240px))}';
 const oldMobile='.art-page-header{padding-right:0}.art-page-visual{display:none}';
 const base='.lab-masthead{}.lab-section-head{}'+oldDesktop+' @media(max-width:600px){'+oldMobile+'}';
 const candidate=s.manualHeaderRepair(base);
 assert.equal(typeof candidate,'string');
 assert.equal(s.manualHeaderRepair(candidate),null);
 assert.equal(s.manualHeaderRepair(base.replace(oldDesktop,'.art-page-header{display:none}')),null);
 assert.equal(s.manualHeaderRepair(base.replace(oldMobile,'.art-page-visual{display:none}')),null);
 assert.match(candidate,/.art-page-header>.container\{padding-right:240px\}/);
 assert.doesNotMatch(candidate,/STEP3 home-ranking-link-tap-v1/);
 assert.equal(s.repair(base),base+s.BLOCK,'existing automatic recipe is unchanged');
});

test('manual category header comparison requires exactly 18 protected screens and non-overlap',()=>{
 const oldDesktop='.art-page-header{position:relative;padding-right:max(260px,calc((100vw - 1180px)/2 + 240px))}';
 const oldMobile='.art-page-header{padding-right:0}.art-page-visual{display:none}';
 const original='.lab-masthead{}.lab-section-head{}'+oldDesktop+' @media(max-width:600px){'+oldMobile+'}';
 const candidate=s.manualHeaderRepair(original);
 const categories=new Set(['/categories/laundry/','/categories/tissue/','/categories/toilet-paper/']);
 const before=s.PAGES.flatMap(path=>s.WIDTHS.map(viewport=>{
  const category=categories.has(path),desktop=viewport>600;
  return {path,viewport,status:'PASS',css_hash:s.sha(original),
    protected_hash:'unchanged',interactions:['compare-save-and-reload-persistence'],
    issues:[],screenshot_hash:'before',dom:{documentWidth:viewport,
      header:category?{titleLeft:100,titleRight:desktop?1100:290,
       visualLeft:desktop?1050:320,visualVisible:desktop}:null}};
 }));
 const after=structuredClone(before);
 for(const screen of after)if(categories.has(screen.path)&&screen.viewport>600)
  screen.dom.header.titleRight=1040;
 assert.equal(s.compareManualHeader(before,after,original,candidate).length,18);
 const reject=mutation=>{const bad=structuredClone(after);mutation(bad);
   assert.throws(()=>s.compareManualHeader(before,bad,original,candidate));};
 reject(a=>a[0].protected_hash='different');
 reject(a=>a[0].interactions=['different']);
 reject(a=>a[0].issues.push({code:'TEXT_OVERLAP_REVIEW',selector:'h1'}));
 reject(a=>a[0].dom.documentWidth=1600);
 reject(a=>a[3].dom.header.titleRight=1200);
 reject(a=>a[4].status='UNAVAILABLE');
 reject(a=>a[5].dom.header.visualVisible=true);
 assert.throws(()=>s.compareManualHeader(before.slice(1),after,original,candidate));
 assert.throws(()=>s.compareManualHeader(before,after,original,candidate+'body{display:none}'));
 const noOverlap=structuredClone(before);
 for(const screen of noOverlap)if(categories.has(screen.path)&&screen.viewport>600)
  screen.dom.header.titleRight=1040;
 assert.throws(()=>s.compareManualHeader(noOverlap,after,original,candidate),
  /baseline overlap/);
});

test('request policy permits images and fixed site only; never affiliate navigation or Google',()=>{
 assert.equal(s.requestPolicy('https://thumbnail.image.rakuten.co.jp/a.jpg','image'),'image');
 for(const url of ['https://thumbnail.image.rakuten.co.jp/a.jpg','https://hb.afl.rakuten.co.jp/hgc/id','https://www.google-analytics.com/g/collect','https://evil.test/data','http://stusaurus.github.io/daily-cost-jp/'])assert.equal(s.requestPolicy(url,'document'),'block');
 assert.equal(s.requestPolicy('https://daily-cost-api.kiyo0625puma.workers.dev/api/product-search?q=test','fetch'),'mock');
 assert.equal(s.requestPolicy('https://stusaurus.github.io/daily-cost-jp/','document'),'site');
});
