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
