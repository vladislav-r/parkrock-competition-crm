"""Reproducible API-only probe. Requires an ALREADY CREATED isolated database.

Run with backend/.venv/Scripts/python.exe scripts/load_probe.py.
Never points writes at the working API/database. Output contains no response bodies/tokens.
"""
import asyncio
import collections
import datetime as dt
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / os.environ.get('LOAD_REPORT_DIR', 'reports/load-2026-09-06')
DB = 'parkrock_load_20260906'
BASE = 'http://127.0.0.1:18082'
os.environ['DATABASE_URL'] = f'postgresql+psycopg://climbhub:climbhub@localhost:5432/{DB}'
sys.path.insert(0, str(ROOT / 'backend'))
import httpx
import psutil
from sqlalchemy import select, func, text
from app.db import SessionLocal, engine
from app.models import Participant, CompetitionSet, Event, EventStage, SetStatus, Club, Ascent, OperationRecord


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def fixtures():
    assert engine.url.database == DB
    with SessionLocal() as db:
        existing = db.scalar(select(CompetitionSet).where(CompetitionSet.name=='LOAD_FIXTURE'))
        if existing:
            return [str(p) for p in db.scalars(select(Participant.id).where(Participant.set_id==existing.id).order_by(Participant.start_number))], str(existing.id)
        event = db.scalar(select(Event))
        event.stage = EventStage.qualification
        event.qualification_started_at = dt.datetime.now(dt.timezone.utc)
        s = CompetitionSet(event_id=event.id, name='LOAD_FIXTURE', time_label='09:00-23:00', capacity=1000, status=SetStatus.draft)
        db.add(s)
        db.flush()
        club = db.scalar(select(Club))
        start = db.scalar(select(func.max(Participant.start_number))) or 0
        people = []
        for i in range(800):
            p = Participant(event_id=event.id, club_id=club.id, set_id=s.id, start_number=start+i+1,
                surname=f'LOAD{i:04d}', name='Probe', birth_date=dt.date(2000,1,1), sex='male',
                club=club.name, checked_in_at=dt.datetime.now(dt.timezone.utc))
            db.add(p)
            people.append(p)
        db.flush()
        ids = [str(p.id) for p in people]
        db.commit()
        return ids, str(s.id)


def pct(values, q):
    a = sorted(values)
    return round(a[min(len(a)-1, int((len(a)-1)*q))], 2) if a else None


class Gateway:
    """HTTP fault proxy; per-device shared bandwidth, delay and lost HTTP replies.
    This models application-visible outages, NOT RF/TCP packet loss or eight physical hosts.
    """
    def __init__(self, profile, upstream):
        self.profile, self.upstream = profile, upstream
        self.locks = [asyncio.Lock() for _ in range(8)]
        self.next_byte = [0.0]*8
        self.faults = collections.Counter()

    async def handle(self, reader, writer):
        try:
            head = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 20)
            lines = head.decode().split('\r\n')
            method, path, _ = lines[0].split(' ')
            headers = dict(line.split(': ',1) for line in lines[1:] if ': ' in line)
            low = {k.lower(): v for k,v in headers.items()}
            body = await reader.readexactly(int(low.get('content-length','0')))
            dev = int(low.get('x-load-device','0'))
            seq = int(low.get('x-load-seq','0'))
            weak = self.profile == 'weak' or self.profile == 'mixed' and dev >= 4
            if weak:
                await asyncio.sleep(0.2 + (seq % 11)*0.01 + len(body)/64000)
            else:
                await asyncio.sleep(0.01)
            # Deterministic request loss, including writes, before forwarding.
            if weak and seq % 97 == 0:
                self.faults['before_forward'] += 1
                return
            r = await self.upstream.request(method, BASE+path, content=body,
                headers={k:v for k,v in headers.items() if k.lower() not in ('host','connection','content-length')})
            if weak and method != 'GET' and seq % 31 == 0:
                self.faults['after_response'] += 1
                return
            await asyncio.sleep(0.2 if weak else 0.01)
            payload = r.content
            writer.write(f'HTTP/1.1 {r.status_code} OK\r\nContent-Length: {len(payload)}\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n'.encode())
            # Shared 2 Mbit/s downlink per weak device; good link 100 Mbit/s.
            rate = 250000 if weak else 12500000
            for pos in range(0,len(payload),16384):
                chunk = payload[pos:pos+16384]
                async with self.locks[dev]:
                    now = time.perf_counter()
                    wait = max(0, self.next_byte[dev]-now)
                    self.next_byte[dev] = max(now,self.next_byte[dev])+len(chunk)/rate
                await asyncio.sleep(wait)
                writer.write(chunk)
                await writer.drain()
        except (Exception, asyncio.CancelledError):
            self.faults['connection_closed_or_upstream_error'] += 1
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ids, set_id = fixtures()
    env = os.environ.copy()
    env['PARKROCK_LOG_FILE'] = str(OUT/'backend-access.log')
    log = (OUT/'backend-stderr.log').open('w',encoding='utf-8')
    proc = subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--port','18082','--no-access-log'],
        cwd=ROOT/'backend', env=env, stdout=log, stderr=log)
    save('environment.json', {'database': DB,'port':18082,'backend_pid':proc.pid,
        'logical_cpus':psutil.cpu_count(),'ram_bytes':psutil.virtual_memory().total,
        'python':sys.version,'participants':806,'routes':20,'uvicorn_workers':1,
        'note':'Same Windows host, shared Docker PostgreSQL; development topology, not VPS.'})
    raw = (OUT/'requests.jsonl').open('w',encoding='utf-8')
    accepted = []
    try:
        async with httpx.AsyncClient(timeout=30, limits=httpx.Limits(max_connections=160,max_keepalive_connections=80)) as direct:
            for _ in range(60):
                try:
                    if (await direct.get(BASE+'/health')).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.5)
            login = await direct.post(BASE+'/api/v1/auth/login',data={'username':'admin@parkrock.test','password':'demo1234'})
            login.raise_for_status()
            auth = {'Authorization':'Bearer '+login.json()['access_token']}
            direct.headers.update(auth)
            e = (await direct.get(BASE+'/api/v1/admin/event')).json()
            routes = [r['id'] for r in e['routes'] if r['is_active']]
            states = [{'version':1,'paid':False,'routes':[]} for _ in ids]
            locks = [asyncio.Lock() for _ in ids]
            summaries=[]
            for profile, duration, rps in [('baseline',30,10),('good',90,100),('weak',90,100),('mixed',90,100)]:
                gateway = Gateway(profile,direct)
                server = await asyncio.start_server(gateway.handle,'127.0.0.1',8102)
                records=[]
                sets={}
                pending=set()
                started=time.perf_counter()
                wall=time.time()
                stop_monitor=asyncio.Event()
                async def monitor():
                    n=0
                    while not stop_monitor.is_set():
                        try:
                            r=await direct.get(BASE+'/metrics',timeout=8)
                            (OUT/f'{profile}-metrics-{n:03d}.prom').write_text(r.text,encoding='utf-8')
                            cpu=psutil.Process(proc.pid).cpu_times()
                            with (OUT/'resources.jsonl').open('a') as f:
                                f.write(json.dumps({'profile':profile,'time':time.time(),'cpu_seconds':cpu.user+cpu.system,
                                    'rss':psutil.Process(proc.pid).memory_info().rss,'host_cpu_pct':psutil.cpu_percent(),
                                    'host_available_ram':psutil.virtual_memory().available})+'\n')
                        except Exception as exc:
                            with (OUT/'resources.jsonl').open('a') as f:
                                f.write(json.dumps({'profile':profile,'time':time.time(),'error':type(exc).__name__})+'\n')
                        n+=1
                        try:
                            await asyncio.wait_for(stop_monitor.wait(),5)
                        except asyncio.TimeoutError:
                            pass
                mon=asyncio.create_task(monitor())
                async with httpx.AsyncClient(timeout=httpx.Timeout(12),limits=httpx.Limits(max_connections=512,max_keepalive_connections=0),headers=auth) as client:
                    async def request(i,due):
                        dev=i%8
                        slot=i%20
                        ix=(i//20*6 + min(max(slot-12,0),5))%len(ids)
                        method='GET'
                        path=['/api/v1/public/results','/api/v1/admin/event','/api/v1/admin/participants?search=LOAD000',
                              '/api/v1/admin/categories','/api/v1/auth/me','/api/v1/admin/participants?search=LOAD001'][slot%6]
                        payload=None
                        oid=str(uuid.uuid4())
                        lock=locks[ix] if 12<=slot<18 else asyncio.Lock()
                        async with lock:
                            state=states[ix]
                            if 12<=slot<16:
                                method='PUT'; path=f'/api/v1/admin/participants/{ids[ix]}/results'
                                payload={'expected_version':state['version'],'completed_route_ids':routes[:1+(i//20)%len(routes)]}
                            elif 16<=slot<18:
                                method='PATCH'; path=f'/api/v1/admin/participants/{ids[ix]}/reception'
                                payload={'expected_version':state['version'],'is_paid':not state['paid']}
                            elif slot==18:
                                method='POST'; path='/api/v1/admin/sets'
                                payload={'name':f'LOAD_{profile}_{i}','start_time':'09:00','end_time':'10:00','capacity':10}
                            elif slot==19:
                                method='DELETE'
                                fut=sets.setdefault(i//20,asyncio.get_running_loop().create_future())
                                try:
                                    created=await asyncio.wait_for(asyncio.shield(fut),40)
                                    path=f"/api/v1/admin/sets/{created['id']}?expected_version={created['version']}"
                                except Exception:
                                    records.append({'i':i,'method':method,'status':'dependency_failed'})
                                    return
                            t=time.perf_counter()
                            rec={'profile':profile,'i':i,'device':dev,'method':method,'route':path.split('?')[0] if method in ('GET','POST') else method+' owned object',
                                 'dispatch_lag_ms':round((t-due)*1000,2),'operation_id':oid if method!='GET' else None}
                            headers={'X-Operation-Id':oid,'X-Load-Device':str(dev),'X-Load-Seq':str(i)}
                            kwargs={'headers':headers}
                            if payload is not None: kwargs['json']=payload
                            response=None
                            try:
                                response=await asyncio.wait_for(client.request(method,'http://127.0.0.1:8102'+path,**kwargs),15)
                                rec['status']=response.status_code
                                rec['bytes']=len(response.content)
                            except Exception as exc:
                                rec['status']=type(exc).__name__
                            rec['latency_ms']=round((time.perf_counter()-t)*1000,2)
                            # Reconcile ambiguous writes with the SAME id after failure (recovered connection).
                            if method!='GET' and (response is None or response.status_code>=500):
                                try:
                                    response=await direct.request(method,BASE+path,**kwargs)
                                    rec['recovery_status']=response.status_code
                                except Exception as exc:
                                    rec['recovery_status']=type(exc).__name__
                            if response is not None and response.status_code<300 and method!='GET':
                                data=response.json()
                                accepted.append({'id':oid,'method':method,'payload':payload,'response':data,'person':ids[ix] if method in ('PUT','PATCH') else None})
                                if method in ('PUT','PATCH'):
                                    state['version']=data['version']
                                    state['paid']=data['is_paid']
                                    if method=='PUT': state['routes']=payload['completed_route_ids']
                                if method=='POST':
                                    fut=sets.setdefault(i//20,asyncio.get_running_loop().create_future())
                                    if not fut.done(): fut.set_result(data)
                            elif method=='POST':
                                fut=sets.setdefault(i//20,asyncio.get_running_loop().create_future())
                                if not fut.done(): fut.set_exception(RuntimeError('create_failed'))
                            if response is not None and response.status_code>=400:
                                rec['error']=response.text[:300]
                            records.append(rec)
                            raw.write(json.dumps(rec)+'\n')
                    total=duration*rps
                    for i in range(total):
                        due=started+i/rps
                        await asyncio.sleep(max(0,due-time.perf_counter()))
                        if len(pending)>=512:
                            records.append({'i':i,'status':'admission_dropped','method':'unknown'})
                            continue
                        task=asyncio.create_task(request(i,due))
                        pending.add(task)
                        task.add_done_callback(pending.discard)
                    await asyncio.gather(*pending)
                stop_monitor.set(); await mon
                server.close(); await server.wait_closed()
                elapsed=time.perf_counter()-started
                summary={'profile':profile,'start_unix':wall,'end_unix':time.time(),'target_rps':rps,'schedule_seconds':duration,
                    'elapsed_with_drain_seconds':round(elapsed,2),'scheduled':total,'statuses':dict(collections.Counter(str(r['status']) for r in records)),
                    'recovery_statuses':dict(collections.Counter(str(r['recovery_status']) for r in records if 'recovery_status' in r)),
                    'faults':dict(gateway.faults),'methods':{},'routes':{}}
                for key,group in [('methods','method'),('routes','route')]:
                    for name in set(r.get(group,'unknown') for r in records):
                        rr=[r for r in records if r.get(group,'unknown')==name]
                        vals=[r['latency_ms'] for r in rr if 'latency_ms' in r]
                        summary[key][name]={'count':len(rr),'p50_ms':pct(vals,.5),'p95_ms':pct(vals,.95),'p99_ms':pct(vals,.99),
                            'statuses':dict(collections.Counter(str(r['status']) for r in rr))}
                summary['dispatch_p95_ms']=pct([r['dispatch_lag_ms'] for r in records if 'dispatch_lag_ms'in r],.95)
                summaries.append(summary); save('summary.json',summaries); raw.flush()
                print(json.dumps({k:v for k,v in summary.items() if k not in ('routes','methods')},ensure_ascii=True),flush=True)
                await asyncio.sleep(3)
            # Verify committed writes and final owned participant state against the database.
            with SessionLocal() as db:
                missing=[]; mismatch=[]
                for a in accepted:
                    op=db.get(OperationRecord,uuid.UUID(a['id']))
                    if op is None: missing.append(a['id'])
                    elif json.loads(op.response_json) != a['response']: mismatch.append(a['id'])
                final_errors=[]
                for ix,pid in enumerate(ids):
                    p=db.get(Participant,uuid.UUID(pid))
                    completed=set(str(x) for x in db.scalars(select(Ascent.route_id).where(Ascent.participant_id==p.id,Ascent.is_completed.is_(True))))
                    if p.version!=states[ix]['version'] or p.is_paid!=states[ix]['paid'] or completed!=set(states[ix]['routes']): final_errors.append(pid)
                owned_sets=db.scalar(select(func.count()).select_from(CompetitionSet).where(CompetitionSet.name.like('LOAD_%'),CompetitionSet.name!='LOAD_FIXTURE'))
                save('integrity.json',{'acknowledged_writes':len(accepted),'missing_operations':missing,'response_mismatches':mismatch,
                    'participant_state_mismatches':final_errors,'remaining_load_sets':owned_sets})
            # Concurrent identical retries and conflicting versions, no UI.
            pid=ids[0]; state=states[0]
            payload={'expected_version':state['version'],'is_paid':not state['paid']}
            oid=str(uuid.uuid4()); url=BASE+f'/api/v1/admin/participants/{pid}/reception'
            replies=await asyncio.gather(*[direct.patch(url,json=payload,headers={'X-Operation-Id':oid}) for _ in range(8)])
            conflict_payload={'expected_version':replies[0].json()['version'],'is_paid':state['paid']}
            conflicting=await asyncio.gather(*[direct.patch(url,json=conflict_payload,headers={'X-Operation-Id':str(uuid.uuid4())}) for _ in range(8)])
            save('concurrency.json',{'identical_retry_statuses':[r.status_code for r in replies],
                'identical_retry_same_response':all(r.json()==replies[0].json() for r in replies),
                'conflicting_version_statuses':[r.status_code for r in conflicting]})
    finally:
        raw.close(); proc.terminate()
        try: proc.wait(15)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait()
        log.close(); engine.dispose()


if __name__=='__main__':
    asyncio.run(main())
