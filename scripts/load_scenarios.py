"""Bounded arrival-rate load/fault test against the load_probe isolated fixture only."""
import asyncio
from collections import Counter
import json
import os
import time
import uuid
import subprocess
import sys
import tempfile
import psutil

from load_probe import ROOT, OUT, DB, BASE, SessionLocal, engine, Participant, CompetitionSet, OperationRecord, Ascent, select, save, pct
import aiohttp
from aiohttp import web

PORT=18082
LOG=None
JOURNAL=None
BACKENDS={}


def start_backend(label):
    OUT.mkdir(parents=True, exist_ok=True)
    env=os.environ.copy()
    runtime=tempfile.TemporaryDirectory(prefix='parkrock-load-runtime-')
    env['PARKROCK_RUNTIME_DIRECTORY']=runtime.name
    env['BACKUP_DIRECTORY']=runtime.name
    env['PARKROCK_LOG_FILE']=str(OUT/f'{label}-access.log')
    log=(OUT/f'{label}-stderr.log').open('w',encoding='utf-8')
    proc=subprocess.Popen([sys.executable,'-m','app.serve','--host','127.0.0.1','--port',str(PORT),'--workers',env.get('LOAD_WORKERS','1')],
        cwd=ROOT/'backend',env=env,stdout=log,stderr=log,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0)
    proc.load_runtime=runtime
    BACKENDS[proc.pid]=(proc,log)
    return proc,log


def stop_backend(proc,log):
    children=psutil.Process(proc.pid).children(recursive=True)
    for child in reversed(children):
        try:child.kill()
        except psutil.NoSuchProcess:pass
    proc.terminate()
    try: proc.wait(3)
    except subprocess.TimeoutExpired: proc.kill();proc.wait()
    psutil.wait_procs(children,timeout=5)
    log.close()
    proc.load_runtime.cleanup()
    BACKENDS.pop(proc.pid,None)


async def ready(client):
    for _ in range(40):
        try:
            async with client.get(BASE+'/health',timeout=aiohttp.ClientTimeout(total=1)) as r:
                if r.status==200: return
        except Exception: pass
        await asyncio.sleep(.25)
    raise RuntimeError('Isolated API did not start')


async def main():
    global LOG,JOURNAL
    OUT.mkdir(parents=True, exist_ok=True)
    LOG=(OUT/'bounded-requests.jsonl').open('w',encoding='utf-8',buffering=1)
    JOURNAL=(OUT/'mutation-journal.jsonl').open('w',encoding='utf-8',buffering=1)
    summaries=[]
    duration=int(os.environ.get('LOAD_DURATION_SECONDS','60'))
    run_prefix=uuid.uuid4().hex[:8]
    for profile in os.environ.get('LOAD_PROFILES','good,weak,mixed').split(','):
        assert engine.url.database==DB
        if os.environ.get('LOAD_CLEAN_FIXTURE')=='1':
            with SessionLocal() as db:
                for item in db.scalars(select(CompetitionSet).where(CompetitionSet.name.like('BOUND_%') | CompetitionSet.name.like('LOAD_%'))):
                    if item.name!='LOAD_FIXTURE':db.delete(item)
                db.commit()
        proc,log=start_backend(profile)
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6),connector=aiohttp.TCPConnector(limit=256)) as upstream:
            await ready(upstream)
            async with upstream.post(BASE+'/api/v1/auth/login',data={'username':'admin@parkrock.test','password':'demo1234'}) as r:
                auth={'Authorization':'Bearer '+(await r.json())['access_token']}
            async with upstream.get(BASE+'/api/v1/admin/event',headers=auth) as r: event=await r.json()
            routes=[r['id'] for r in event['routes'] if r['is_active']]
            with SessionLocal() as db:
                ss=db.scalar(select(CompetitionSet).where(CompetitionSet.name=='LOAD_FIXTURE'))
                people=list(db.scalars(select(Participant).where(Participant.set_id==ss.id).order_by(Participant.start_number)))
                states=[{'id':str(p.id),'version':p.version,'paid':p.is_paid} for p in people]
            locks=[asyncio.Lock() for _ in states]
            wire_locks=[asyncio.Lock() for _ in range(8)]
            next_send=[0.]*8
            faults=Counter()
            wire_bytes=[0]*8
            async def gateway(request):
                device=int(request.headers['X-Load-Device']); seq=int(request.headers['X-Load-Seq'])
                weak=profile=='weak' or profile=='mixed' and device>=4
                body=await request.read()
                await asyncio.sleep((.2+seq%11*.01+len(body)/64000) if weak else .01)
                if weak and seq%97==0:
                    faults['before_forward']+=1
                    request.transport.close()
                    return web.Response()
                try:
                    async with upstream.request(request.method,BASE+request.path_qs,data=body,auto_decompress=False,headers={
                        'Authorization':auth['Authorization'],'X-Operation-Id':request.headers.get('X-Operation-Id',''),
                        'Content-Type':'application/json'}) as r:
                        data=await r.read();status=r.status;encoding=r.headers.get('Content-Encoding')
                    if weak and request.method!='GET' and seq%31==0:
                        faults['after_response']+=1
                        request.transport.close()
                        return web.Response()
                    await asyncio.sleep(.2 if weak else .01)
                    response=web.StreamResponse(status=status,headers={'Content-Type':'application/json','Content-Length':str(len(data))})
                    if encoding:response.headers['Content-Encoding']=encoding
                    await response.prepare(request)
                    for pos in range(0,len(data),16384):
                        chunk=data[pos:pos+16384]
                        async with wire_locks[device]:
                            now=time.perf_counter();wait=max(0,next_send[device]-now)
                            next_send[device]=max(now,next_send[device])+len(chunk)/(250000 if weak else 12500000)
                        await asyncio.sleep(wait);await response.write(chunk);wire_bytes[device]+=len(chunk)
                    await response.write_eof()
                    return response
                except Exception:
                    faults['upstream_or_transport_error']+=1
                    return web.Response(status=502)
            app=web.Application();app.router.add_route('*','/{tail:.*}',gateway)
            runner=web.AppRunner(app,access_log=None,shutdown_timeout=1);await runner.setup()
            await web.TCPSite(runner,'127.0.0.1',18102).start()
            records=[];writes=[];created={};pending=set();health=[]
            stop=asyncio.Event();started=time.perf_counter();wall=time.time()
            async def watchdog():
                failures=0
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as c:
                    while not stop.is_set():
                        await asyncio.sleep(3)
                        try:
                            async with c.get(BASE+'/health') as r: ok=r.status==200
                        except Exception: ok=False
                        failures=0 if ok else failures+1
                        health.append({'at':time.time(),'healthy':ok})
                        if failures>=3:stop.set()
            watch=asyncio.create_task(watchdog())
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=7),connector=aiohttp.TCPConnector(limit=256)) as client:
                async def one(i,due):
                    slot=i%20;device=i%8;ix=(i//20*6+max(0,min(slot-12,5)))%len(states)
                    state=states[ix];method='GET';body=None
                    path=['/api/v1/public/results','/api/v1/admin/event','/api/v1/admin/participants?search=LOAD000',
                        '/api/v1/admin/categories','/api/v1/auth/me','/api/v1/admin/participants?search=LOAD001'][slot%6]
                    async with locks[ix] if 12<=slot<18 else asyncio.Lock():
                        if 12<=slot<16:
                            method='PUT';path=f"/api/v1/admin/participants/{state['id']}/results"
                            body={'expected_version':state['version'],'completed_route_ids':routes[:1+i//20%len(routes)]}
                        elif 16<=slot<18:
                            method='PATCH';path=f"/api/v1/admin/participants/{state['id']}/reception"
                            body={'expected_version':state['version'],'is_paid':not state['paid']}
                        elif slot==18:
                            method='POST';path='/api/v1/admin/sets'
                            body={'name':f'BOUND_{run_prefix}_{profile}_{i}','start_time':'10:00','end_time':'11:00','capacity':10}
                        elif slot==19:
                            method='DELETE'
                            for _ in range(70):
                                if i//20 in created:break
                                await asyncio.sleep(.1)
                            data=created.get(i//20)
                            if not data:
                                rec={'profile':profile,'i':i,'method':method,'status':'dependency_skipped'}
                                records.append(rec);LOG.write(json.dumps(rec)+'\n');return
                            path=f"/api/v1/admin/sets/{data['id']}?expected_version={data['version']}"
                        oid=str(uuid.uuid4());t=time.perf_counter()
                        rec={'profile':profile,'i':i,'device':device,'method':method,'route':path.split('?')[0] if method in ('GET','POST') else method+' owned object',
                            'operation_id':oid if method!='GET' else None,'dispatch_lag_ms':round((t-due)*1000,2),'start_unix':time.time()}
                        command={'profile':profile,'id':oid,'method':method,'path':path,'payload':body}
                        if method!='GET':writes.append(command);JOURNAL.write(json.dumps(command)+'\n')
                        try:
                            async with client.request(method,'http://127.0.0.1:18102'+path,json=body,headers={**auth,
                                    'X-Operation-Id':oid,'X-Load-Seq':str(i),'X-Load-Device':str(device)}) as r:
                                data=await r.read();rec['status']=r.status;rec['bytes']=len(data)
                                if r.status==200 and method!='GET':
                                    result=json.loads(data);command['acknowledged']=result
                                    if method in ('PUT','PATCH'):state.update(version=result['version'],paid=result['is_paid'])
                                    if method=='POST':created[i//20]=result
                        except Exception as exc:rec['status']=type(exc).__name__
                        rec['latency_ms']=round((time.perf_counter()-t)*1000,2)
                        records.append(rec);LOG.write(json.dumps(rec)+'\n')
                for i in range(duration*100):
                    due=started+i/100
                    await asyncio.sleep(max(0,due-time.perf_counter()))
                    if stop.is_set():break
                    if len(pending)>=256:
                        rec={'profile':profile,'i':i,'method':'unknown','status':'admission_dropped'}
                        records.append(rec);LOG.write(json.dumps(rec)+'\n');continue
                    task=asyncio.create_task(one(i,due));pending.add(task);task.add_done_callback(pending.discard)
                issued=i+1
                await asyncio.gather(*pending)
            stop.set();watch.cancel();await asyncio.gather(watch,return_exceptions=True)
            await runner.cleanup()
        stop_backend(proc,log)
        summary={'profile':profile,'start_unix':wall,'end_unix':time.time(),'target_rps':100,'planned_seconds':duration,
            'scheduled_slots':issued,'early_stop':issued<duration*100,'elapsed_seconds':round(time.perf_counter()-started,2),
            'statuses':dict(Counter(str(r['status']) for r in records)),'faults':dict(faults),'health':health,'wire_bytes_by_device':wire_bytes,
            'dispatch_p95_ms':pct([r['dispatch_lag_ms'] for r in records if 'dispatch_lag_ms'in r],.95),'methods':{},'routes':{}}
        for key,field in [('methods','method'),('routes','route')]:
            for name in set(r.get(field,'unknown') for r in records):
                rr=[r for r in records if r.get(field,'unknown')==name];v=[r['latency_ms'] for r in rr if 'latency_ms'in r]
                summary[key][name]={'count':len(rr),'p50_ms':pct(v,.5),'p95_ms':pct(v,.95),'p99_ms':pct(v,.99),
                    'statuses':dict(Counter(str(r['status']) for r in rr))}
        # Reconcile after restarting the isolated API. Every unknown mutation is retried with identical payload/id.
        save('bounded-summary.json', summaries+[summary])
        proc,log=start_backend(profile+'-recovery')
        recovery=Counter();missing_ack=[];replayed=0;recovery_errors=[]
        def read_committed():
            with SessionLocal() as db:
                return {str(op.id):json.loads(op.response_json) for op in db.scalars(select(OperationRecord).where(
                    OperationRecord.id.in_([uuid.UUID(w['id']) for w in writes]))) if op.response_json}
        # Do not block the async client's loop with thousands of synchronous
        # queries while its persistent HTTP connections expire server-side.
        committed_operations=await asyncio.to_thread(read_committed)
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10),headers=auth) as c:
            await ready(c)
            for w in writes:
                committed=w['id'] in committed_operations
                if 'acknowledged'in w and (not committed or committed_operations[w['id']]!=w['acknowledged']):missing_ack.append(w['id'])
                if 'acknowledged'not in w:
                    try:
                        async with c.request(w['method'],BASE+w['path'],json=w['payload'],headers={'X-Operation-Id':w['id']}) as r:
                            data=await r.read();recovery[str(r.status)]+=1
                            if committed and r.status==200:replayed+=1
                    except Exception as exc:
                        recovery[type(exc).__name__]+=1
                        recovery_errors.append({'id':w['id'],'method':w['method'],'error':type(exc).__name__,'committed_before_retry':committed})
            # Strong concurrency check on an owned participant, outside throughput sample.
            with SessionLocal() as db:p=db.get(Participant,uuid.UUID(states[0]['id']));version=p.version;paid=p.is_paid
            payload={'expected_version':version,'is_paid':not paid};oid=str(uuid.uuid4());url=BASE+f'/api/v1/admin/participants/{p.id}/reception'
            async def patch(key,body):
                try:
                    async with c.patch(url,json=body,headers={'X-Operation-Id':key}) as r:return r.status,await r.json()
                except Exception as exc:
                    return type(exc).__name__,None
            same=await asyncio.gather(*[patch(oid,payload) for _ in range(8)])
            first_success=next((r for r in same if r[0]==200),None)
            conflict=await asyncio.gather(*[patch(str(uuid.uuid4()),{'expected_version':first_success[1]['version'],'is_paid':paid}) for _ in range(8)]) if first_success else []
        stop_backend(proc,log)
        summary['integrity']={'attempted_mutations':len(writes),'acknowledged':sum('acknowledged'in w for w in writes),
            'missing_or_mismatched_acknowledged':missing_ack,'recovery_statuses':dict(recovery),'already_committed_replayed':replayed,
            'recovery_errors':recovery_errors,
            'concurrent_same_id_statuses':[r[0]for r in same],'concurrent_same_id_equal':all(r==same[0]for r in same),
            'concurrent_different_id_statuses':[r[0]for r in conflict]}
        summaries.append(summary);save('bounded-summary.json',summaries)
        print(json.dumps({k:v for k,v in summary.items() if k not in ('methods','routes','health')},ensure_ascii=True),flush=True)
    LOG.close();JOURNAL.close();engine.dispose()


if __name__=='__main__':
    try:
        asyncio.run(main())
    finally:
        for proc,log in list(BACKENDS.values()):
            stop_backend(proc,log)
