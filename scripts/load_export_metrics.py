"""Persist the temporary Prometheus time series before removing its container."""
import asyncio,json,time
import aiohttp
from load_probe import OUT,save

async def main():
    start_file=OUT/('bounded-summary.json' if (OUT/'bounded-summary.json').exists() else 'summary.json')
    start=json.loads(start_file.read_text())[0]['start_unix']
    queries={
        'target_up':'up',
        'backend_responses':'sum by (method,route,status)(parkrock_http_requests_total)',
        'backend_latency_buckets':'sum by (le,route)(parkrock_http_request_duration_seconds_bucket)',
        'backend_rss':'parkrock_process_resident_memory_bytes',
        'backend_cpu_seconds':'parkrock_process_cpu_seconds_total',
        'backend_inflight':'fastapi_requests_in_progress',
        'db_request_sessions':'parkrock_db_request_sessions',
        'db_requests_waiting':'parkrock_db_requests_waiting',
        'db_checked_out':'parkrock_db_connections_checked_out',
        'db_connections':'pg_stat_database_numbackends{datname="parkrock_load_20260906"}',
        'db_activity':'sum by(state)(pg_stat_activity_count{datname="parkrock_load_20260906"})',
        'db_commits':'pg_stat_database_xact_commit{datname="parkrock_load_20260906"}',
        'db_rollbacks':'pg_stat_database_xact_rollback{datname="parkrock_load_20260906"}',
        'db_deadlocks':'pg_stat_database_deadlocks{datname="parkrock_load_20260906"}',
        'db_blocks_read':'pg_stat_database_blks_read{datname="parkrock_load_20260906"}',
        'db_blocks_hit':'pg_stat_database_blks_hit{datname="parkrock_load_20260906"}',
    }
    data={}
    async with aiohttp.ClientSession() as c:
        for name,query in queries.items():
            async with c.get('http://127.0.0.1:19090/api/v1/query_range',params={'query':query,'start':start,'end':time.time(),'step':5}) as r:
                data[name]={'query':query,'response':await r.json()}
    save('prometheus-series.json',data)
    print({k:len(v['response'].get('data',{}).get('result',[])) for k,v in data.items()})

if __name__=='__main__':asyncio.run(main())
