"""Local development database configuration shared by startup and migrations."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import quote, urlsplit, unquote

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
LEGACY_FILE = ROOT / ".wellspring-postgres.json"
KEYS = ("WELLSPRING_DB_HOST", "WELLSPRING_DB_PORT", "WELLSPRING_DB_NAME", "WELLSPRING_DB_USER")


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or key in values:
            raise ValueError(f".env 第 {number} 行格式无效或配置重复")
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise ValueError(f".env 第 {number} 行引号或转义无效") from None
        elif value.startswith("'"):
            if len(value) < 2 or value[-1] != "'":
                raise ValueError(f".env 第 {number} 行引号不匹配")
            value = value[1:-1]
        if not isinstance(value, str) or "\x00" in value:
            raise ValueError(f".env 第 {number} 行必须为无 NUL 的字符串")
        values[key] = value
    return values


def write_local_env(host: str, port: int, database: str, username: str, path: Path = ENV_FILE, password: str = ""):
    fields = dict(zip(KEYS, (host, str(port), database, username)))
    if any(not value or any(char in value for char in "\r\n'\"") for value in fields.values()):
        raise ValueError("数据库连接参数格式无效")
    if any(char in password for char in "\r\n\x00"):
        raise ValueError("数据库密码格式无效")
    with open(path, "x", encoding="utf-8", newline="\n", opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
        stream.write("# 本机开发配置；此文件包含密码，不要提交或分享。\n")
        stream.writelines(f"{key}={value}\n" for key, value in fields.items())
        stream.write(f"WELLSPRING_DB_PASSWORD={json.dumps(password, ensure_ascii=False)}\n")


def migrate_legacy_config(root: Path = ROOT) -> bool:
    env_file, legacy = root / ".env", root / ".wellspring-postgres.json"
    if env_file.exists() or not legacy.is_file():
        return False
    config = json.loads(legacy.read_text(encoding="utf-8"))
    if set(config) != {"host", "port", "database", "username"} or config["host"] != "127.0.0.1" or config["port"] != 5432:
        raise ValueError("旧 PostgreSQL 配置无效")
    write_local_env(config["host"], config["port"], config["database"], config["username"], env_file)
    return True


def database_environment(base: dict[str, str], root: Path = ROOT) -> dict[str, str]:
    env = base.copy()
    if env.get("DATABASE_URL"):
        return env
    env_path = root / ".env"
    if not env_path.exists() and (root / ".wellspring-postgres.json").exists():
        migrate_legacy_config(root)
    if not env_path.exists():
        return env
    config = read_env(env_path)
    if "DATABASE_URL" in config:
        raise ValueError(".env 请使用 WELLSPRING_DB_* 连接参数，不要写入 DATABASE_URL")
    if config.get("WELLSPRING_DB_PASSWORD_FILE"):
        raise ValueError("请移除 WELLSPRING_DB_PASSWORD_FILE，并在 .env 中设置 WELLSPRING_DB_PASSWORD")
    if not any(config.get(key) for key in KEYS):
        if (root / ".wellspring-postgres.json").exists():
            raise ValueError(".env 未配置数据库，旧配置仍存在；请补齐 .env，避免连接错误数据库")
        return env
    if not all(config.get(key) for key in KEYS):
        raise ValueError(".env 中数据库地址、端口、名称和账号必须全部填写")
    host, port, database, username = (config[key] for key in KEYS)
    if host != "127.0.0.1" or not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ValueError("本机开发数据库地址或端口无效")
    password = config.get("WELLSPRING_DB_PASSWORD", "")
    if not password or any(char in password for char in "\r\n\x00"):
        raise ValueError("请在 .env 中设置非空的 WELLSPRING_DB_PASSWORD")
    env["DATABASE_URL"] = f"postgresql+psycopg://{quote(username, safe='')}:{quote(password, safe='')}@{host}:{port}/{quote(database, safe='')}"
    return env


def database_target(env: dict[str, str]) -> str:
    """Describe only the selected location; never return credentials/query options."""
    value = env.get("DATABASE_URL", "sqlite:///./wellspring-dev.db")
    parsed = urlsplit(value)
    if parsed.scheme.startswith("sqlite"):
        return "SQLite：" + unquote(parsed.path.lstrip("/"))
    try:
        port = f":{parsed.port}" if parsed.port else ""
    except ValueError:
        raise ValueError("数据库端口格式无效") from None
    return f"{parsed.scheme}：{parsed.hostname or ''}{port}/{unquote(parsed.path.lstrip('/'))}"
