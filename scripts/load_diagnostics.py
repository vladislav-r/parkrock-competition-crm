"""Read-only differential probes on the isolated load database; no application edits."""
import asyncio,json,os,subprocess,sys,time
from collections import Counter
import aiohttp
from sqlalchemy import event as sa_event, text
from load_probe import ROOT,OUT,DB,BASE,SessionLocal,engine,select,CompetitionSet,Event,save,pct
from load_scenarios import start_backend,stop_backend,ready

async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # Remove only empty synthetic sets in the disposable clone, restoring equal test cardinality.
    with SessionLocal() as db:
        for s in db.scalars(select(CompetitionSet).where(CompetitionSet.name.like('BOUND_%') | CompetitionSet.name.like('LOAD_%'))):
            if s.name!='LOAD_FIXTURE':db.delete(s)
        db.commit()
    results=[]
    mode=os.environ.get('DIAG_ONLY')
    cases=[('business_workers4',False)] if mode=='workers' else [('business_default',False)] if mode=='verify' else [('business_stack',False)] if mode=='stack' else [('business_admission10',False)] if mode else [('light',False),('business_default',False),('business_pool64',True)]
    if mode=='sql':cases=[]
    for label,large in cases:
        if label=='business_workers4':
            log=(OUT/f'{label}-stderr.log').open('w');proc=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--port','18082','--workers','4','--no-access-log'],cwd=ROOT/'backend',env=os.environ.copy(),stdout=log,stderr=log)
        elif label=='business_stack':
            code="import faulthandler; faulthandler.dump_traceback_later(10); import uvicorn; uvicorn.run('app.main:app',port=18082,access_log=False)"
            log=(OUT/f'{label}-stderr.log').open('w');proc=subprocess.Popen([sys.executable,'-c',code],cwd=ROOT/'backend',env=os.environ.copy(),stdout=log,stderr=log)
        elif label=='business_admission10':
            code="import asyncio; from app.main import app; gate=asyncio.Semaphore(10)\n@app.middleware('http')\nasync def admission(request,call_next):\n async with gate:\n  return await call_next(request)\nimport uvicorn; uvicorn.run(app,port=18082,access_log=False)"
            log=(OUT/f'{label}-stderr.log').open('w');proc=subprocess.Popen([sys.executable,'-c',code],cwd=ROOT/'backend',env=os.environ.copy(),stdout=log,stderr=log)
        elif large:
            code="from sqlalchemy import create_engine; import app.db as d; d.engine=create_engine(d.settings.database_url,pool_pre_ping=True,pool_size=64,max_overflow=0); d.SessionLocal.configure(bind=d.engine); import uvicorn; uvicorn.run('app.main:app',port=18082,access_log=False)"
            log=(OUT/f'{label}-stderr.log').open('w');proc=subprocess.Popen([sys.executable,'-c',code],cwd=ROOT/'backend',env=os.environ.copy(),stdout=log,stderr=log)
        else:proc,log=start_backend(label)
        rr=[];pending=set();start_wall=time.time()
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6),connector=aiohttp.TCPConnector(limit=256)) as c:
            await ready(c)
            async with c.post(BASE+'/api/v1/auth/login',data={'username':'admin@parkrock.test','password':'demo1234'}) as r:auth={'Authorization':'Bearer '+(await r.json())['access_token']}
            started=time.perf_counter()
            async def req(i,due):
                path='/api/v1/auth/me' if label=='light' else ['/api/v1/public/results','/api/v1/admin/event','/api/v1/admin/participants?search=LOAD000','/api/v1/admin/categories','/api/v1/auth/me'][i%5]
                t=time.perf_counter()
                try:
                    async with c.get(BASE+path,headers=auth) as r:await r.read();status=r.status
                except Exception as exc:status=type(exc).__name__
                rr.append({'status':status,'ms':(time.perf_counter()-t)*1000,'lag_ms':(t-due)*1000,'path':path})
            for i in range(1500):
                due=started+i/100;await asyncio.sleep(max(0,due-time.perf_counter()))
                if len(pending)>=256:rr.append({'status':'dropped'});continue
                t=asyncio.create_task(req(i,due));pending.add(t);t.add_done_callback(pending.discard)
            await asyncio.gather(*pending)
            with SessionLocal() as db:
                db_states=[dict(r._mapping)for r in db.execute(text("select state,wait_event_type,count(*) from pg_stat_activity where datname=:name group by 1,2"),{'name':DB})]
        stop_backend(proc,log)
        result={'label':label,'start_unix':start_wall,'end_unix':time.time(),'scheduled':1500,'statuses':dict(Counter(str(r['status'])for r in rr)),
            'p95_ms':pct([r['ms']for r in rr if 'ms'in r],.95),'dispatch_p95_ms':pct([r['lag_ms']for r in rr if 'lag_ms'in r],.95),'db_states':db_states}
        results.append(result);save('differential.json' if mode=='verify' or not mode else 'stack-experiment.json' if mode=='stack' else 'admission-experiment.json',results);print(json.dumps(result),flush=True)
    if mode and mode!='sql':return
    # Measure SQL amplification in actual endpoint functions, outside the timed loads.
    from app.routers import admin,public,admin_categories
    sql_results=[]
    for label,call in [('public_results',lambda db:public.results(db=db)),('admin_event',lambda db:admin.event_dashboard(db=db)),
                       ('categories',lambda db:admin_categories.read_categories(db,db.scalar(select(Event)))),
                       ('participants_10',lambda db:admin.participants(search='LOAD000',db=db)),('participants_all',lambda db:admin.participants(db=db))]:
        count=[0]
        def before(*args):count[0]+=1
        sa_event.listen(engine,'before_cursor_execute',before)
        t=time.perf_counter()
        with SessionLocal() as db:
            response=call(db)
            data=[x.model_dump(mode='json')for x in response] if isinstance(response,list) else response.model_dump(mode='json')
        sa_event.remove(engine,'before_cursor_execute',before)
        sql_results.append({'endpoint':label,'sql_queries':count[0],'duration_ms':round((time.perf_counter()-t)*1000,2),
            'json_bytes':len(json.dumps(data,ensure_ascii=False,separators=(',',':')).encode())})
    save('sql-profile.json',sql_results);print(json.dumps(sql_results),flush=True)

if __name__=='__main__':asyncio.run(main())
