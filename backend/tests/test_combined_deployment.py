"""Verify the deployment entry point in an isolated process."""
import os
from pathlib import Path
import subprocess
import sys


def test_combined_application_serves_frontend_and_api(tmp_path):
    (tmp_path / 'index.html').write_text('<h1>前端测试</h1>', encoding='utf-8')
    assets = tmp_path / 'assets'
    assets.mkdir()
    (assets / 'test.js').write_text('export default 1', encoding='utf-8')
    deploy = Path(__file__).resolve().parents[2] / 'deploy' / 'offline'
    script = '''
from fastapi.testclient import TestClient
from combined_app import app
with TestClient(app) as client:
    page = client.get('/')
    assert page.status_code == 200 and '前端测试' in page.text
    assert page.headers['cache-control'] == 'no-cache'
    assert page.headers['x-frame-options'] == 'DENY'
    assert "script-src 'self'" in page.headers['content-security-policy']
    assert client.get('/assets/test.js').status_code == 200
    assert client.get('/assets/missing.js').status_code == 404
    api = client.get('/api/health')
    assert api.status_code == 200 and api.json()['status'] == 'ok'
    assert api.headers['cache-control'] == 'no-store'
    assert client.get('/api/ready').status_code == 503
    assert client.get('/api/missing').status_code == 404
'''
    env = {**os.environ, 'DATABASE_URL': 'sqlite://', 'WELLSPRING_STATIC_DIR': str(tmp_path), 'PYTHONPATH': str(deploy)}
    subprocess.run([sys.executable, '-c', script], env=env, check=True, capture_output=True, text=True, encoding='utf-8')
