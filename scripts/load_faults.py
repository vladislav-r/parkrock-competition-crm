"""Eight virtual judges: lost responses after commit, same-id replays, and concurrent saves."""
import asyncio,datetime as dt,json,uuid
from sqlalchemy import func
import aiohttp
from aiohttp import web
from load_probe import OUT,BASE,DB,SessionLocal,select,save,engine
from load_scenarios import start_backend,stop_backend,ready
from app.models import (Event,EventStage,Participant,AgeGroup,Admin,FinalRoute,FinalCategoryRoute,
    QualificationCategorySnapshot,QualificationResultSnapshot,FinalCategoryResult,FinalRouteAttempt,OperationRecord)


async def main():
    assert engine.url.database == DB
    with SessionLocal() as db:
        e=db.scalar(select(Event));e.stage=EventStage.final;e.final_started_at=dt.datetime.now(dt.timezone.utc)
        group=db.scalar(select(AgeGroup).where(AgeGroup.sex=='male',AgeGroup.min_age==19))
        category=db.scalar(select(QualificationCategorySnapshot).where(QualificationCategorySnapshot.age_group_id==group.id))
        if category is None:category=QualificationCategorySnapshot(event_id=e.id,age_group_id=group.id,name=group.name,sex=group.sex,min_age=group.min_age,
            max_age=group.max_age,sort_order=group.sort_order,finalist_count=16,settings_json='{}',signature='load-fault-test')
        db.add(category);db.flush()
        routes=list(db.scalars(select(FinalRoute).order_by(FinalRoute.number).limit(4)))
        for assignment in db.scalars(select(FinalCategoryRoute).where(FinalCategoryRoute.age_group_id==group.id)):db.delete(assignment)
        db.flush()
        for route in routes:db.add(FinalCategoryRoute(event_id=e.id,age_group_id=group.id,final_route_id=route.id))
        admin=db.scalar(select(Admin).where(Admin.email=='admin@parkrock.test'));admin.assigned_final_route_id=routes[0].id
        people=list(db.scalars(select(Participant).where(Participant.surname.like('LOAD%')).order_by(Participant.start_number).limit(16)))
        final_ids=[]
        for i,p in enumerate(people):
            existing=db.scalar(select(FinalCategoryResult).where(FinalCategoryResult.participant_id==p.id))
            if existing:
                for attempt in db.scalars(select(FinalRouteAttempt).where(FinalRouteAttempt.final_category_result_id==existing.id)):
                    db.delete(attempt)
                final_ids.append(str(existing.id));continue
            q=QualificationResultSnapshot(event_id=e.id,category_snapshot_id=category.id,participant_id=p.id,start_number=p.start_number,
                surname=p.surname,name=p.name,club=p.club,completed_count=1,points=100,place=i+1,is_finalist=True,exit_order=16-i)
            db.add(q);db.flush()
            f=FinalCategoryResult(event_id=e.id,category_snapshot_id=category.id,qualification_result_snapshot_id=q.id,participant_id=p.id)
            db.add(f);db.flush();final_ids.append(str(f.id))
        route_id=routes[0].id;db.commit()
    proc,log=start_backend('judge-faults')
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as c:
            await ready(c)
            async with c.post(BASE+'/api/v1/auth/login',data={'username':'admin@parkrock.test','password':'demo1234'}) as r:
                auth={'Authorization':'Bearer '+(await r.json())['access_token']}
            upstream_status=[]
            async def lost_reply(request):
                async with c.put(BASE+request.path,json=await request.json(),headers={**auth,'X-Operation-Id':request.headers['X-Operation-Id']}) as r:
                    await r.read();upstream_status.append(r.status)
                request.transport.close()
                return web.Response()
            app=web.Application();app.router.add_put('/api/v1/judge/results/{id}',lost_reply)
            runner=web.AppRunner(app,access_log=None);await runner.setup();await web.TCPSite(runner,'127.0.0.1',18103).start()
            lost=[];retry=[];ops=[]
            # Sequential commits make each fault unambiguous; eight independent synthetic device commands.
            for i,fid in enumerate(final_ids[:8]):
                with SessionLocal() as db:version=db.get(FinalCategoryResult,uuid.UUID(fid)).version
                oid=str(uuid.uuid4());ops.append(oid);body={'expected_version':version,'zone_attempt':1,'top_attempt':i+1}
                try:
                    async with c.put(f'http://127.0.0.1:18103/api/v1/judge/results/{fid}',json=body,headers={'X-Operation-Id':oid}) as r:
                        await r.read();lost.append(r.status)
                except Exception as exc:lost.append(type(exc).__name__)
                async with c.put(BASE+f'/api/v1/judge/results/{fid}',json=body,headers={**auth,'X-Operation-Id':oid}) as r:
                    await r.read();retry.append(r.status)
            await runner.cleanup()
            commands=[]
            with SessionLocal() as db:
                for fid in final_ids[8:]:commands.append((fid,db.get(FinalCategoryResult,uuid.UUID(fid)).version,str(uuid.uuid4())))
            async def concurrent(item):
                fid,version,oid=item
                try:
                    async with c.put(BASE+f'/api/v1/judge/results/{fid}',json={'expected_version':version,'zone_attempt':1,'top_attempt':2},
                            headers={**auth,'X-Operation-Id':oid}) as r:return {'status':r.status,'body':(await r.text())[:200] if r.status!=200 else 'ok'}
                except Exception as exc:return {'status':type(exc).__name__}
            concurrent_results=await asyncio.gather(*[concurrent(item) for item in commands])
            with SessionLocal() as db:
                counts=[db.scalar(select(func.count()).select_from(FinalRouteAttempt).where(FinalRouteAttempt.final_category_result_id==uuid.UUID(fid),FinalRouteAttempt.final_route_id==route_id))for fid in final_ids]
                values=[{'zone':x.zone_attempt,'top':x.top_attempt}for fid in final_ids[:8] for x in db.scalars(select(FinalRouteAttempt).where(FinalRouteAttempt.final_category_result_id==uuid.UUID(fid)))]
                saved=sum(db.get(OperationRecord,uuid.UUID(oid)) is not None for oid in ops)
            save('judge-faults.json',{'upstream_status_before_connection_cut':upstream_status,'client_lost_reply':lost,'same_id_retry_status':retry,
                'saved_operation_count':saved,'attempt_counts_per_finalist':counts,'saved_values_first_eight':values,'concurrent_eight':concurrent_results})
            print(json.dumps({'upstream':upstream_status,'retry':retry,'counts':counts,'concurrent':concurrent_results}),flush=True)
    finally:stop_backend(proc,log);engine.dispose()

if __name__=='__main__':asyncio.run(main())
