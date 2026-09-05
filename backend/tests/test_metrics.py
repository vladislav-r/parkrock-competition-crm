def test_metrics_include_http_request_counters(client):
    response = client.get("/health")
    assert response.status_code == 200

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert metrics.headers["content-type"].startswith("text/plain")
    assert 'parkrock_http_requests_total{method="GET",route="/health",status="200"}' in metrics.text
    assert 'parkrock_http_request_duration_seconds_count{method="GET",route="/health"}' in metrics.text
    assert 'fastapi_app_info{app_name="parkrock-backend"} 1.0' in metrics.text
    assert 'fastapi_requests_total{app_name="parkrock-backend",method="GET",path="/health"}' in metrics.text
    assert 'fastapi_responses_total{app_name="parkrock-backend",method="GET",path="/health",status_code="200"}' in metrics.text
    assert 'fastapi_requests_duration_seconds_count{app_name="parkrock-backend",path="/health"}' in metrics.text
    assert "parkrock_process_resident_memory_bytes" in metrics.text
    assert "parkrock_process_cpu_seconds_total" in metrics.text
