"""Check real worker replacement, merged metrics and graceful shutdown on the isolated API."""
import asyncio
import os
from pathlib import Path
import signal
import time

import aiohttp
import psutil
from prometheus_client.parser import text_string_to_metric_families
from load_probe import OUT, BASE, save
from load_scenarios import start_backend, stop_backend, ready


async def main():
    outcomes = []
    for workers in (1, 4):
        os.environ['LOAD_WORKERS'] = str(workers)
        proc, log = start_backend(f'runtime-{workers}')
        runtime = Path(proc.load_runtime.name)
        try:
            async with aiohttp.ClientSession() as client:
                await ready(client)

                async def metrics():
                    async with client.get(BASE+'/metrics') as response:
                        assert response.status == 200
                        text = await response.text()
                    return [sample for family in text_string_to_metric_families(text) for sample in family.samples]

                def counter(samples):
                    return sum(s.value for s in samples if s.name == 'parkrock_http_requests_total' and s.labels.get('route') == '/health')

                before = counter(await metrics())
                async def hit():
                    async with client.get(BASE+'/health') as response:
                        assert response.status == 200
                        await response.read()
                await asyncio.gather(*[hit() for _ in range(100)])
                after = counter(await metrics())
                assert after-before == 100, (before, after)
                files = list(runtime.rglob('gauge_livemax_*.db'))
                deadline = time.monotonic()+10
                while len(files) != workers and time.monotonic() < deadline:
                    await asyncio.sleep(.25)
                    files = list(runtime.rglob('gauge_livemax_*.db'))
                assert len(files) == workers
                result = {'workers': workers, 'health_requests': 100, 'merged_counter_delta': after-before}
                if workers == 4:
                    dead_file = files[0]
                    dead_pid = int(dead_file.stem.split('_')[-1])
                    psutil.Process(dead_pid).kill()
                    deadline = time.monotonic()+15
                    while time.monotonic() < deadline:
                        files = list(runtime.rglob('gauge_livemax_*.db'))
                        if not dead_file.exists() and len(files) == 4:
                            break
                        await asyncio.sleep(.25)
                    assert not dead_file.exists() and len(files) == 4
                    samples = await metrics()
                    assert counter(samples) == after
                    assert next(s.value for s in samples if s.name == 'fastapi_app_info') == 1
                    await hit()
                    result.update(worker_replaced=True, dead_live_gauges_removed=True, counters_preserved=True)
            children = psutil.Process(proc.pid).children(recursive=True)
            proc.send_signal(signal.CTRL_BREAK_EVENT if os.name=='nt' else signal.SIGTERM)
            await asyncio.to_thread(proc.wait, 30)
            assert proc.returncode == 0, proc.returncode
            assert not list(runtime.iterdir()), 'Runtime metrics were not removed on graceful shutdown'
            assert all(not child.is_running() for child in children)
            result['graceful_shutdown_clean'] = True
            outcomes.append(result)
        finally:
            if proc.poll() is None:
                stop_backend(proc, log)
            else:
                log.close()
                proc.load_runtime.cleanup()
    save('runtime-check.json', outcomes)
    print(outcomes)


if __name__ == '__main__':
    asyncio.run(main())
