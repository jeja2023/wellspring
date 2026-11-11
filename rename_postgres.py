"""Safely rename the existing local development database and login role."""
from __future__ import annotations

from datetime import datetime
import getpass
import os
from pathlib import Path
import subprocess
import sys

from local_config import read_env

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / '.env'
PG_BIN = Path(r'C:\Program Files\PostgreSQL\18\bin')
OLD = 'wellspring_dev'
NEW = 'wellspring'


def main():
    try:
        import psycopg
        from psycopg import sql
    except ImportError:
        raise SystemExit('请使用 backend/.venv 中的 Python 运行此脚本。')

    config = read_env(ENV_FILE)
    if (config.get('WELLSPRING_DB_HOST'), config.get('WELLSPRING_DB_PORT'), config.get('WELLSPRING_DB_NAME'), config.get('WELLSPRING_DB_USER')) != ('127.0.0.1', '5432', NEW, OLD):
        raise SystemExit('本机配置与预期迁移状态不一致，未更改数据库或账号。')
    password = config.get('WELLSPRING_DB_PASSWORD', '')
    if not password:
        raise SystemExit('请先在 .env 中填写当前 wellspring_dev 数据库账号密码。')
    admin = input('PostgreSQL 管理员账号 [postgres]: ').strip() or 'postgres'
    admin_password = getpass.getpass('PostgreSQL 管理员密码: ')
    if not admin_password:
        raise SystemExit('管理员密码不能为空。')
    options = dict(host='127.0.0.1', port=5432, dbname='postgres', user=admin, password=admin_password, connect_timeout=5)

    try:
        with psycopg.connect(**options, autocommit=True) as db:
            is_super = db.execute('SELECT rolsuper FROM pg_roles WHERE rolname = current_user').fetchone()
            if not is_super or not is_super[0]:
                raise SystemExit('此操作需要 PostgreSQL 超级用户；未更改数据库或账号。')
            databases = {r[0] for r in db.execute("SELECT datname FROM pg_database WHERE datname IN ('wellspring', 'wellspring_dev')")}
            roles = {r[0] for r in db.execute("SELECT rolname FROM pg_roles WHERE rolname IN ('wellspring', 'wellspring_dev')")}
            if databases != {OLD} or roles != {OLD}:
                raise SystemExit('目标名称已存在或原数据库／账号不存在；未进行更名，请人工核查。')
            count = db.execute('SELECT count(*) FROM pg_stat_activity WHERE datname = %s', (OLD,)).fetchone()[0]
            if count:
                raise SystemExit(f'原数据库仍有 {count} 个连接，请先停止清源及其他数据库客户端。')
            dump = PG_BIN / 'pg_dump.exe'
            restore = PG_BIN / 'pg_restore.exe'
            if not dump.is_file() or not restore.is_file():
                raise SystemExit('未找到 PostgreSQL 18 的备份工具，未执行更名。')
            backup_dir = ROOT / 'backend' / 'backups'
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup = backup_dir / f"wellspring-dev-before-rename-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.dump"
            child_env = os.environ.copy()
            child_env.update(PGHOST='127.0.0.1', PGPORT='5432', PGUSER=OLD, PGPASSWORD=password, PGCONNECT_TIMEOUT='5')
            with backup.open('xb') as stream:
                result = subprocess.run([str(dump), '--format=custom', '--no-password', '--dbname', OLD], stdout=stream, stderr=subprocess.DEVNULL, env=child_env)
            if result.returncode:
                raise SystemExit('备份失败，未执行更名；请检查数据库账号密码。')
            result = subprocess.run([str(restore), '--list', str(backup)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if result.returncode:
                raise SystemExit('备份检查失败，未执行更名。')
            if db.execute('SELECT count(*) FROM pg_stat_activity WHERE datname = %s', (OLD,)).fetchone()[0]:
                raise SystemExit('备份完成，但原数据库出现新连接，未执行更名。')
            db.execute(sql.SQL('ALTER DATABASE {} RENAME TO {}').format(sql.Identifier(OLD), sql.Identifier(NEW)))
            print(f'数据库已更名；备份文件：{backup}', flush=True)
            try:
                with db.transaction():
                    db.execute("SET LOCAL password_encryption = 'scram-sha-256'")
                    db.execute(sql.SQL('ALTER ROLE {} PASSWORD {}').format(sql.Identifier(OLD), sql.Literal(password)))
                    db.execute(sql.SQL('ALTER ROLE {} RENAME TO {}').format(sql.Identifier(OLD), sql.Identifier(NEW)))
            except psycopg.Error:
                raise SystemExit('数据库已更名，但账号未更名；.env 中仍使用原账号，请检查权限后处理。')
    except psycopg.Error as exc:
        raise SystemExit(f'数据库操作失败（{exc.__class__.__name__}）；请检查连接、权限及当前名称。')

    # Preserve all other settings and the password without printing them.
    lines = ENV_FILE.read_text(encoding='utf-8-sig').splitlines()
    indexes = [i for i, line in enumerate(lines) if line.strip().startswith('WELLSPRING_DB_USER=')]
    if len(indexes) != 1:
        raise SystemExit('数据库和账号已更名，请手动将 .env 中的 WELLSPRING_DB_USER 设置为 wellspring。')
    lines[indexes[0]] = 'WELLSPRING_DB_USER=wellspring'
    ENV_FILE.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    try:
        with psycopg.connect(host='127.0.0.1', port=5432, dbname=NEW, user=NEW, password=password, connect_timeout=5) as db:
            db.execute('SELECT 1')
    except psycopg.Error:
        raise SystemExit('名称已更新，但新账号连接验证失败，请检查认证设置。')
    print('数据库和数据库账号均已更名为 wellspring，连接验证通过。')


if __name__ == '__main__':
    main()
