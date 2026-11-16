'use strict';
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(path.join(__dirname,'../site/app.js'),'utf8');
const values=new Map();const ctx={URL,localStorage:{getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v)},document:{querySelector:()=>null}};
vm.runInNewContext(source.slice(0,source.indexOf('function render('))+'\nglobalThis.api={dailyFor,today,myGoals,browse,moreIdeas,gold,trackedObjective,taskDetails,dailyCheckKey,BROWSE_GROUPS,VIEWS,setBucket:v=>dailyBucket=v};',ctx);
const a=ctx.api,c={id:'sample',addonVersion:'1.10.0',exportedAt:'2026-11-16T22:00:00Z',character:{name:'Example',level:23},professions:[{name:'Tailoring',isPrimary:true,skillLineID:197,skill:94,maxSkill:150},{name:'Enchanting',isPrimary:true,skillLineID:333,skill:115,maxSkill:150}],fieldPlan:{materials:[],spots:[]}};
for(const version of [1,2,3]){
  c.dailyPlan={version,day:'2026-11-16',mode:'gold',today:[{id:'gold:sell:1',title:'Sell spare cloth',kind:'Sell',open:'Gold',why:'Surplus',action:'Review unit prices'}],projects:[]};
  assert.equal(a.dailyFor(c),c.dailyPlan,`daily schema ${version} is supported`);
  assert.match(a.today(c),/Make gold/);assert.match(a.today(c),/Sell spare cloth/);assert.doesNotMatch(a.today(c),/minute session|older snapshot/);
}
c.dailyPlan.today=Array.from({length:5},(_,i)=>({id:'gold:sell:'+i,title:'Saved task '+i,kind:'Sell',open:'Gold'}));
let html=a.today(c);assert.equal((html.match(/featured-task/g)||[]).length,1);assert.match(html,/2 more tasks in your saved checklist/);assert.match(html,/Saved task 4/,'additional saved tasks are not lost');
assert.match(html,/Reviewed on this device/);assert.doesNotMatch(html,/Mark complete/);
c.dailyPlan.camp={id:'old',name:'Chosen camp',zone:'Zone',chosen:true};
c.dailyPlan.soon=[{id:'upgrade:42',title:'Pinned upgrade',kind:'Gear',open:'Gear',pinned:true,why:'<script>bad</script>',action:'<img onerror=bad>'}];
assert.match(a.trackedObjective(c),/Pinned upgrade/);assert.doesNotMatch(a.trackedObjective(c),/Chosen camp/,'explicit task wins over old camp');
html=a.taskDetails(c,'upgrade:42');assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>|<img/);assert.match(html,/#upgrades\/sample/);
assert.equal(a.taskDetails(c,'missing'),null);
c.dailyPlan.soon=[];assert.match(a.trackedObjective(c),/Chosen camp/);delete c.dailyPlan.camp;assert.match(a.trackedObjective(c),/Choose one thing/);
html=a.myGoals(c);assert.match(html,/Tailoring/);assert.match(html,/Enchanting/);assert.match(html,/94/);assert.match(html,/115/);assert.match(html,/successful crafting casts/);
html=a.myGoals({...c,professions:[]});assert.match(html,/No primary professions/);
const olderProfessions={...c,professions:c.professions.map(({skillLineID,...p})=>p),dailyPlan:{...c.dailyPlan,soon:[{id:'profession:tailor',title:'Tailoring: train next rank'},{id:'profession:enchant',title:'Enchanting: learn next recipe'}]}};
html=a.myGoals(olderProfessions);assert.match(html,/Tailoring: train next rank/);assert.match(html,/Enchanting: learn next recipe/);assert.doesNotMatch(html,/Saved task 0/,'missing profession IDs must not match unrelated tasks');
html=a.browse(c);for(const group of a.BROWSE_GROUPS)for(const [view]of group.items){assert.ok(a.VIEWS[view],view+' has a route');assert.match(html,new RegExp('#'+view+'/sample'));}
assert.match(a.gold(c),/Saved task 0/);assert.match(a.gold(c),/not live auction prices/);
a.setBucket('snoozed');c.dailyPlan.snoozed=[{id:'snoozed',title:'For later'}];assert.match(a.moreIdeas(c),/For later/);
values.set(a.dailyCheckKey(c,c.dailyPlan),JSON.stringify(['gold:sell:0']));assert.match(a.today(c),/locally-checked/);
assert.notEqual(a.dailyCheckKey(c,c.dailyPlan),a.dailyCheckKey({...c,id:'other'},c.dailyPlan));
assert.notEqual(a.dailyCheckKey(c,c.dailyPlan),a.dailyCheckKey(c,{day:'2026-11-17'}));
const index=fs.readFileSync(path.join(__dirname,'../site/index.html'),'utf8');assert.deepEqual([...index.matchAll(/data-view="([^"]+)"/g)].map(m=>m[1]),['today','goals','browse']);
console.log('PASS journal: schemas 1–3, gold focus, three-step default, retained overflow, both professions, explicit tracking, browse routes, escaped details, and isolated browser reviews');
