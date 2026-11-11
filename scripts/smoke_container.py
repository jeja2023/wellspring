"""Run a built image against disposable synthetic SQLite, optionally browser workflows."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
from uuid import uuid4

SEED_AND_SERVE = '''
import os
os.environ['DATABASE_URL'] = 'sqlite:////tmp/synthetic.db'
from alembic import command
from alembic.config import Config
command.upgrade(Config('/app/alembic.ini'), 'head')
from wellspring.db import SessionLocal
from wellspring.models import Organization, User
from wellspring.security import password_hash
with SessionLocal() as db:
    org, other = Organization(name='浏览器回归组织'), Organization(name='隔离组织')
    db.add_all([org, other]); db.flush()
    encoded = password_hash('synthetic-test-password')
    db.add_all([User(username=name, org_id=organization.id, password_hash=encoded)
                for name, organization in (('alice', org), ('receiver', org), ('outsider', other))])
    db.add(User(username="superadmin",org_id=org.id,password_hash=encoded,is_admin=True))
    db.commit()
import uvicorn
uvicorn.run('combined_app:app', host='0.0.0.0', port=8000, log_level='warning')
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', required=True)
    parser.add_argument('--browser', action='store_true')
    parser.add_argument('--startup-timeout', type=float, default=180, help='Cold container startup deadline in seconds')
    args = parser.parse_args()
    if args.startup_timeout <= 0:
        parser.error('--startup-timeout must be positive')
    name = 'wellspring-smoke-' + uuid4().hex
    subprocess.run(['docker', 'run', '--detach', '--rm', '--name', name,
                    '--tmpfs', '/tmp:rw,size=64m',
                    '-p', '127.0.0.1::8000', '--entrypoint', 'python', args.image,
                    '-c', SEED_AND_SERVE], check=True, capture_output=True)
    try:
        mapping = subprocess.run(['docker', 'port', name, '8000/tcp'], check=True, capture_output=True, text=True).stdout.strip()
        base = 'http://' + mapping
        deadline = time.monotonic() + args.startup_timeout
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(base + '/api/ready', timeout=2) as response:
                    if response.status == 200:
                        break
            except Exception:
                time.sleep(1)
        else:
            raise RuntimeError('Disposable application did not become ready')
        with urllib.request.urlopen(base, timeout=5) as response:
            assert 'text/html' in response.headers['content-type']
            assert response.headers['X-Frame-Options'] == 'DENY'
            assert "worker-src 'self'" in response.headers['Content-Security-Policy']
        with urllib.request.urlopen(base + '/api/health', timeout=5) as response:
            assert json.load(response)['status'] == 'ok'
        if args.browser:
            frontend = Path(__file__).resolve().parents[1] / 'frontend'
            # Each disposable container needs its own artifacts, including when
            # diagnostics/CI runs overlap. Playwright cleans its output on start.
            output = frontend / 'test-results' / name
            subprocess.run([shutil.which('npm.cmd' if os.name == 'nt' else 'npm'), 'run', 'test:e2e', '--', '--output', str(output)],
                           cwd=frontend, env={**os.environ, 'WELLSPRING_E2E_BASE_URL': base}, check=True)
        print('Built image: readiness, static assets, security headers and requested workflows passed')
    except BaseException:
        logs = subprocess.run(['docker', 'logs', '--tail', '60', name], capture_output=True, text=True)
        print('Disposable container diagnostics:\n' + logs.stdout + logs.stderr, file=sys.stderr)
        raise
    finally:
        subprocess.run(['docker', 'rm', '--force', name], check=True, capture_output=True)


if __name__ == '__main__':
    main()
