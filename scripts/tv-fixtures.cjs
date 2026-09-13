// Isolated browser acceptance harness: node scripts/tv-fixtures.cjs
// Proxies a production preview (npm start -- --port 3003) at 127.0.0.1:3002.
// No requests reach the database. POST /__control adjusts in-memory fixtures.
const http = require('node:http');
let state = { count:50, revision:0, offline:false, stage:'final', finalGroups:true, added:false, delay:0 };
let active=0, maxActive=0, requests=0;
const names=['Мальчики 10-12','Девочки 10-12','Юноши 13-14'];
function rows(name,count) {
  return Array.from({length:count},(_,i)=>({
    participant_id:`${name}-${i}`,start_number:i+1,full_name:i===2?'Константинопольский-Крестовоздвиженский Александр':`Участник ${String(i+1).padStart(3,'0')}`,
    club:i===2?'Спортивный клуб скалолазания и альпинизма «Длинное название команды»':'Клуб скалолазания',group_name:name,
    place:i===count-1?null:i<2?1:i+1,points:i===count-1?null:1000-i*10+state.revision,
    medal:i===3?'gold':i===4?'silver':i===5?'bronze':null,is_finalist:i<2,has_result:i<count-1,
    score:100-i/10,qualification_place:i+1,exit_order:count-i,attempts:[],top_count:4,zone_count:4,
  }));
}
const injection=`<script>(()=>{const original=window.fetch.bind(window);window.fetch=(input,init)=>{const url=new URL(typeof input==='string'?input:input.url||String(input),location.href);if(url.pathname.startsWith('/api/v1/'))return original('/__fixture'+url.pathname+url.search,init);return original(input,init)}})()</script>`;
http.createServer(async(req,res)=>{
  if(req.url==='/__control'&&req.method==='POST') {
    let body='';for await(const part of req)body+=part;
    state={...state,...JSON.parse(body)};res.end(JSON.stringify(state));return;
  }
  if(req.url==='/__stats'){res.end(JSON.stringify({active,maxActive,requests,state}));return;}
  if(req.url.startsWith('/__fixture')){
    active++;requests++;maxActive=Math.max(maxActive,active);
    await new Promise(resolve=>setTimeout(resolve,state.delay));
    active--;
    if(state.offline){res.writeHead(503,{'Content-Type':'application/json'});res.end('{"detail":"Fixture offline"}');return;}
    const url=new URL(req.url,'http://127.0.0.1');
    const groups=state.added?[...names,'Новая группа']:names;
    let data;
    if(url.pathname.endsWith('/final-results'))data={category_name:url.searchParams.get('group'),routes:[],results:rows(url.searchParams.get('group'),6),updated_at:null};
    else data={event_id:'tv-fixture',event_title:'ПаркРок · Тестовый показ',stage:state.stage,groups,final_groups:state.stage==='final'&&state.finalGroups?[names[1]]:[],sets:[],results:[...rows(names[0],state.count),...rows(names[1],2),...(state.added?rows('Новая группа',1):[])],updated_at:null};
    res.writeHead(200,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(data));return;
  }
  try {
    const response=await fetch(`http://localhost:3003${req.url}`);
    const type=response.headers.get('content-type')||'';
    res.writeHead(response.status,{'Content-Type':type,'Cache-Control':'no-store'});
    if(type.includes('text/html'))res.end((await response.text()).replace('<head>','<head>'+injection));
    else res.end(Buffer.from(await response.arrayBuffer()));
  }catch(error){res.writeHead(502);res.end(String(error));}
}).listen(3002,'127.0.0.1',()=>console.log('TV fixture UI: http://127.0.0.1:3002/tv'));
