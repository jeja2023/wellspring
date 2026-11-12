"""Preview or explicitly insert synthetic data into the local development database."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))


def main():
    parser = argparse.ArgumentParser(description='补齐本机开发库的虚构测试数据；默认只预览，重复执行不重复插入')
    parser.add_argument('--owner', default='admin', help='数据归属的现有超级管理员账号（不修改账号）')
    parser.add_argument('--apply', action='store_true', help='备份后在单个事务内实际写入')
    args = parser.parse_args()
    from local_config import database_environment, database_target
    config = database_environment(os.environ.copy())
    url = config.get('DATABASE_URL', 'sqlite:///' + (ROOT / 'backend/wellspring-dev.db').as_posix())
    from sqlalchemy import create_engine, select, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session
    from wellspring.demo_data import DATASET, DemoBuilder, seed_demo_data
    from wellspring.models import Audit, User
    from wellspring.startup_migrations import backup_database
    target = make_url(url)
    if target.get_backend_name() not in {'sqlite','postgresql'} or (target.get_backend_name() == 'postgresql' and target.host not in {'127.0.0.1','localhost','::1'}):
        raise SystemExit('此工具仅适用于本机 SQLite/PostgreSQL 开发库')
    engine = create_engine(url, hide_parameters=True)
    print('目标：' + database_target({**config, 'DATABASE_URL':url}), flush=True)
    report_path = None
    try:
        with engine.connect() as connection:
            if connection.scalar(text('SELECT version_num FROM alembic_version')) != '0028':
                raise SystemExit('数据库须已迁移到 0028；测试数据工具不执行结构迁移')
            connection.rollback()
            if target.get_backend_name() == 'postgresql':
                connection.execute(text("SELECT pg_advisory_lock(hashtext('wellspring-demo-seed'))"))
                connection.commit()
            with Session(bind=connection, expire_on_commit=False) as db:
                actor = db.scalar(select(User).where(User.username == args.owner))
                if not actor:raise SystemExit('指定的归属账号不存在')
                if db.get(Audit, DemoBuilder(db,actor,datetime.now(timezone.utc)).identity('completed')):
                    print('当前组织已存在完整演示数据，本次不重复插入。');return
                db.rollback()
                backup = None
                if args.apply:
                    backup = backup_database(connection, target, ROOT/'backend/backups/demo-data', ['0028'], 'demo-data-v1')
                    connection.rollback()
                result = seed_demo_data(db, actor)
                print(json.dumps({'mode':'apply' if args.apply else 'preview','dataset':DATASET,
                                  'owner':args.owner,'inserted':result['inserted']},ensure_ascii=False),flush=True)
                if not args.apply:
                    db.rollback();print('预览完成，未写入数据库。');return
                folder=ROOT/'releases/demo-data';folder.mkdir(parents=True,exist_ok=True)
                stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
                report_path=folder/f'{stamp}-{os.urandom(4).hex()}.json'
                result['backup']=str(backup)
                # Never print generated credentials or commit them to source control.
                with open(report_path,'x',encoding='utf-8',opener=lambda path,flags:os.open(path,flags,0o600)) as stream:
                    json.dump(result,stream,ensure_ascii=False,indent=2)
                try:db.commit()
                except BaseException:
                    report_path.unlink(missing_ok=True);raise
                print(f'已完成；账号、随机密码及数量报告：{report_path}',flush=True)
            if target.get_backend_name() == 'postgresql':
                connection.execute(text("SELECT pg_advisory_unlock(hashtext('wellspring-demo-seed'))"));connection.commit()
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
