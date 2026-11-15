"""Binary-safe Compose backups and isolated, disposable PostgreSQL restore drills."""
import sys

if __name__ == "__main__" and not sys.flags.isolated:
    raise SystemExit("Run with python -I; untrusted bundle modules must not be imported")

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from uuid import uuid4

HERE = Path(__file__).resolve().parent


def run(command, **kwargs):
    if command[0] == "docker":
        filename = "docker.exe" if os.name == "nt" else "docker"
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            path = Path(directory)
            if not path.is_absolute() or path.resolve().is_relative_to(HERE):
                continue
            candidate = (path / filename).resolve()
            if candidate.is_file() and not candidate.is_relative_to(HERE) and os.access(candidate, os.X_OK):
                command = [str(candidate), *command[1:]]
                break
        else:
            raise ValueError("未找到包外可信 PATH 中的 Docker 可执行文件")
    return subprocess.run(command, check=True, **kwargs)


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup(env_file, output):
    output = output.resolve()
    digest_file = output.with_suffix(output.suffix + ".sha256")
    if output.exists() or digest_file.exists():
        raise ValueError("备份或摘要文件已存在，不覆盖")
    prefix = ["docker", "compose", "--env-file", str(env_file.resolve(strict=True)), "-f", str(HERE / "compose.yaml"), "exec", "-T", "db"]
    version = run([*prefix, "psql", "-X", "-A", "-t", "-U", "wellspring_owner", "-d", "wellspring", "-c", "SHOW server_version_num"], capture_output=True, text=True).stdout.strip()
    if not version.isdecimal() or int(version) // 10000 != 18:
        raise ValueError("备份工具只支持本部署方案的 PostgreSQL 18")
    command = [*prefix, "pg_dump", "-U", "wellspring_owner", "-Fc", "wellspring"]
    temporary = output.with_name(output.name + "." + uuid4().hex + ".partial")
    temporary_digest = temporary.with_suffix(".sha256.partial")
    published_digest = False
    try:
        with open(temporary, "xb", opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
            run(command, stdout=stream)
            stream.flush()
            os.fsync(stream.fileno())
        digest = sha(temporary)
        with temporary_digest.open("x", encoding="ascii") as stream:
            stream.write(f"{digest}  {output.name}\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Hard-link publication is atomic and fails if either final name exists.
        # Unlike replace(), this cannot overwrite a concurrent/previous backup.
        os.link(temporary_digest, digest_file)
        published_digest = True
        os.link(temporary, output)
    except BaseException:
        if published_digest:
            digest_file.unlink(missing_ok=True)
        raise
    finally:
        temporary.unlink(missing_ok=True)
        temporary_digest.unlink(missing_ok=True)
    print(f"备份完成：{output}；请运行 drill 实际恢复验证")


def drill(dump, image, expected_sha, report):
    dump = dump.resolve(strict=True)
    digest = sha(dump)
    if digest.lower() != expected_sha.lower():
        raise ValueError("备份摘要不匹配")
    if report.exists():
        raise ValueError("演练报告已存在，不覆盖")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/@:-]*", image):
        raise ValueError("镜像引用格式无效")
    metadata = json.loads(run(["docker", "image", "inspect", image], capture_output=True, text=True).stdout)[0]
    if metadata.get("Os") != "linux" or metadata.get("Architecture") not in {"amd64", "arm64"}:
        raise ValueError("恢复演练需要已审核的 Linux amd64/arm64 镜像")
    version = run(["docker", "run", "--rm", "--pull", "never", "--network", "none", "--entrypoint", "postgres", image, "--version"], capture_output=True, text=True).stdout
    if not re.search(r"\b18\.", version):
        raise ValueError("恢复演练只支持 PostgreSQL 18 镜像")
    name = "wellspring-restore-drill-" + uuid4().hex
    started = time.monotonic()
    created = False
    try:
        # No host ports, network, existing volume or source database is mounted.
        run(["docker", "run", "--detach", "--pull", "never", "--name", name, "--network", "none",
             "--tmpfs", "/var/lib/postgresql/data", "-e", "POSTGRES_HOST_AUTH_METHOD=trust",
             "-e", "POSTGRES_USER=wellspring_owner", "-e", "POSTGRES_DB=wellspring", image], capture_output=True)
        created = True
        for _ in range(60):
            try:
                run(["docker", "exec", name, "pg_isready", "-U", "wellspring_owner", "-d", "wellspring"], capture_output=True)
                break
            except subprocess.CalledProcessError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("隔离数据库启动超时")
        with dump.open("rb") as stream:
            run(["docker", "exec", "-i", name, "pg_restore", "--exit-on-error", "--no-owner", "--no-privileges",
                 "-U", "wellspring_owner", "-d", "wellspring"], stdin=stream, capture_output=True)
        def query(sql):
            return run(["docker", "exec", name, "psql", "-X", "-v", "ON_ERROR_STOP=1", "-A", "-t", "-U", "wellspring_owner", "-d", "wellspring", "-c", sql], capture_output=True, text=True).stdout.strip()
        tables = query("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").splitlines()
        counts = {table: int(query('SELECT count(*) FROM public."' + table.replace('"', '""') + '"')) for table in tables}
        revision = query("SELECT version_num FROM alembic_version")
        result = {"status": "passed", "checked_at": datetime.now(timezone.utc).isoformat(),
                  "dump_sha256": digest, "image_id": metadata["Id"], "server_version": query("SHOW server_version"),
                  "migration": revision, "table_counts": counts,
                  "elapsed_seconds": round(time.monotonic() - started, 2),
                  "limits": "验证数据库可恢复、表计数及迁移版本；不替代应用权限/业务验收或外部文件恢复"}
        with report.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
        print(f"隔离恢复演练通过：{report}")
    finally:
        if created:
            run(["docker", "rm", "--force", name], capture_output=True)


def main():
    parser = argparse.ArgumentParser()
    actions = parser.add_subparsers(dest="action", required=True)
    create = actions.add_parser("backup")
    create.add_argument("--env-file", required=True, type=Path)
    create.add_argument("--output", required=True, type=Path)
    restore = actions.add_parser("drill")
    restore.add_argument("--dump", required=True, type=Path)
    restore.add_argument("--postgres-image", required=True)
    restore.add_argument("--sha256", required=True)
    restore.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    if args.action == "backup":
        backup(args.env_file, args.output)
    else:
        drill(args.dump, args.postgres_image, args.sha256, args.report)


if __name__ == "__main__":
    main()
