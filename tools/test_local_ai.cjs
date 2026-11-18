const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(path.join(__dirname,'../site/app.js'),'utf8');
const ctx={URL,document:{querySelector:()=>null},localStorage:{getItem:()=>null}};
vm.runInNewContext(source.slice(0,source.indexOf('function render('))+'\nglobalThis.api={advisor,localAICard,aiCurrent};',ctx);
const c={id:'test',character:{name:'Test'}};
assert.match(ctx.api.advisor(c),/Waiting/);
c.localAI={schemaVersion:1,generatedAt:1,expiresAt:2,snapshotAt:'2026-11-18T00:00:00Z',summary:'<script>bad</script>',
 recommendations:[{title:'<img src=x>',taskID:'test',reason:'Check prices',action:'Review deposits',evidenceIDs:['item:1']}],
 evidence:[{id:'item:1',title:'Unsafe link',url:'javascript:alert(1)',confidence:'Fallback'}],knowledge:{},notices:[]};
let html=ctx.api.advisor(c);assert.match(html,/Expired analysis/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>|<img|javascript:/);
c.localAI.expiresAt=Date.now()/1000+1000;assert.equal(ctx.api.aiCurrent(c),true);
c.localAI.evidence[0].url='https://www.wowhead.com/forever/item=1';html=ctx.api.advisor(c);assert.match(html,/rel="noopener noreferrer"/);
assert.match(html,/Reasons, actions and quantities/);
console.log('PASS local advisor: empty, expiry, escaped model/source text, exact source hosts and transparent explanations');
