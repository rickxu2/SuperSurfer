const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const source=fs.readFileSync(require('node:path').join(__dirname,'../ui/provider-choices.js'),'utf8');
const load=()=>import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
test('backend picker includes only verified connected providers, preserves disabled pinned identity',async()=>{
 const {providerChoices}=await load(),labels={codex:'Codex',claude:'Claude',antigravity:'Google',cursor:'Cursor'};
 const accounts={codex:{account:{type:'chatgpt'}},claude:{account:null,login_required:true},antigravity:{account:{type:'antigravity'},reconnect_required:true},cursor:{account:{type:'cursor'},transport_error:true}};
 assert.deepEqual(providerChoices(labels,accounts).map(x=>x.id),['codex']);
 const pinned=providerChoices(labels,accounts,'antigravity',true);assert.equal(pinned[1].disabled,true);assert.match(pinned[1].label,/check Settings/);
 accounts.antigravity.reconnect_required=false;assert.deepEqual(providerChoices(labels,accounts).map(x=>x.id),['codex','antigravity']);
 accounts.codex.login_required=true;assert.deepEqual(providerChoices(labels,accounts).map(x=>x.id),['antigravity']);
 assert.deepEqual(providerChoices(labels,{}),[]);
});
