import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import pytest

spec = importlib.util.spec_from_file_location('wellspring_local_config', Path(__file__).resolve().parents[2] / 'local_config.py')
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


def test_legacy_configuration_migrates_and_requires_password(tmp_path):
    legacy = {'host': '127.0.0.1', 'port': 5432, 'database': 'wellspring_dev', 'username': 'wellspring_dev'}
    (tmp_path / '.wellspring-postgres.json').write_text(json.dumps(legacy), encoding='utf-8')
    with pytest.raises(ValueError, match='WELLSPRING_DB_PASSWORD'):
        config.database_environment({}, root=tmp_path)
    assert (tmp_path / '.wellspring-postgres.json').exists()
    assert config.migrate_legacy_config(tmp_path) is False


def test_env_password_and_explicit_environment_override(tmp_path):
    config.write_local_env('127.0.0.1', 5432, 'dev', 'user', tmp_path / '.env', password='a#b:@"\\')
    assert ':a%23b%3A%40%22%5C@' in config.database_environment({}, root=tmp_path)['DATABASE_URL']
    assert config.database_environment({'DATABASE_URL':'sqlite:///chosen.db'}, root=tmp_path)['DATABASE_URL'] == 'sqlite:///chosen.db'


def test_incomplete_config_and_missing_password_fail_closed(tmp_path):
    (tmp_path / '.env').write_text('WELLSPRING_DB_USER=user\n', encoding='utf-8')
    with pytest.raises(ValueError, match='必须全部填写'):
        config.database_environment({}, root=tmp_path)
    (tmp_path / '.env').write_text('WELLSPRING_DB_HOST=127.0.0.1\nWELLSPRING_DB_PORT=5432\nWELLSPRING_DB_NAME=dev\nWELLSPRING_DB_USER=user\nWELLSPRING_DB_PASSWORD=\n', encoding='utf-8')
    with pytest.raises(ValueError, match='WELLSPRING_DB_PASSWORD'):
        config.database_environment({}, root=tmp_path)


def test_old_password_file_and_duplicate_keys_rejected(tmp_path):
    (tmp_path / '.env').write_text('WELLSPRING_DB_PASSWORD_FILE=secret\n', encoding='utf-8')
    with pytest.raises(ValueError, match='移除'):
        config.database_environment({}, root=tmp_path)
    (tmp_path / '.env').write_text('WELLSPRING_DB_USER=a\nWELLSPRING_DB_USER=b\n', encoding='utf-8')
    with pytest.raises(ValueError, match='重复'):
        config.database_environment({}, root=tmp_path)


def test_target_description_excludes_password_and_query_secrets():
    target = config.database_target({'DATABASE_URL': 'postgresql+psycopg://user:secret@localhost:5432/example?password=also-secret'})
    assert target == 'postgresql+psycopg：localhost:5432/example'
    assert 'secret' not in target


def test_ai_settings_forwarded_from_local_env_with_explicit_override(tmp_path):
    (tmp_path/'.env').write_text('WELLSPRING_AI_API_KEY=synthetic-local-key\nWELLSPRING_AI_ALLOWED_HOSTS=127.0.0.1,model.internal\nUNRELATED=value\n',encoding='utf-8')
    result=config.ai_environment({'DATABASE_URL':'sqlite://','WELLSPRING_AI_API_KEY':'explicit-key'},root=tmp_path)
    assert result['WELLSPRING_AI_API_KEY']=='explicit-key'
    assert result['WELLSPRING_AI_ALLOWED_HOSTS']=='127.0.0.1,model.internal'
    assert result['DATABASE_URL']=='sqlite://' and 'UNRELATED' not in result


@pytest.mark.parametrize('arguments,expected', [
    ([], ['-m', 'wellspring.startup_migrations', '--manual']),
    (['--check'], ['-m', 'alembic', 'check']),
    (['--bootstrap'], ['-m', 'wellspring.bootstrap']),
    (['--bootstrap', '--initial-admin'], ['-m', 'wellspring.bootstrap', '--initial-admin']),
])
def test_database_commands_share_env_without_exposing_password(tmp_path, monkeypatch, capsys, arguments, expected):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root))
    spec = importlib.util.spec_from_file_location('audit_migrate', root / 'migrate.py')
    command = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(command)
    config.write_local_env('127.0.0.1', 55432, 'synthetic', 'user', tmp_path / '.env', password='synthetic-secret')
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.setattr(command, 'database_environment', lambda base: config.database_environment(base, root=tmp_path))
    monkeypatch.setattr(command, 'VENV_PYTHON', Path(sys.executable))
    monkeypatch.setattr(sys, 'argv', ['migrate.py', *arguments])
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0)
    monkeypatch.setattr(command.subprocess, 'run', run)
    assert command.main() == 0
    assert calls[0][0][1:] == expected
    assert calls[0][1]['env']['DATABASE_URL'] == 'postgresql+psycopg://user:synthetic-secret@127.0.0.1:55432/synthetic'
    assert 'synthetic-secret' not in capsys.readouterr().out


def test_old_migration_name_forwards_to_stable_entry_point(monkeypatch, capsys):
    import runpy
    import types
    path = Path(__file__).resolve().parents[2] / 'migrate_dev.py'
    entry = types.ModuleType('migrate')
    calls = []
    entry.main = lambda: calls.append('forwarded') or 7
    monkeypatch.setitem(sys.modules, 'migrate', entry)
    monkeypatch.setattr(sys, 'argv', ['migrate_dev.py', '--check'])
    with pytest.raises(SystemExit) as result:
        runpy.run_path(str(path), run_name='__main__')
    assert result.value.code == 7 and calls == ['forwarded']
    assert 'python migrate.py' in capsys.readouterr().err


def test_offline_map_settings_forward_without_replacing_process_configuration(tmp_path):
    (tmp_path/'.env').write_text('WELLSPRING_MAP_TILE_DIR=E:/synthetic tiles\nWELLSPRING_MAP_TILE_CRS=GCJ02\nWELLSPRING_MAP_MAX_ZOOM=16\nWELLSPRING_MAP_CENTER=120.06,31.55\nWELLSPRING_MAP_INITIAL_ZOOM=11\n',encoding='utf-8')
    result=config.ai_environment({'WELLSPRING_MAP_MAX_ZOOM':'15'},root=tmp_path)
    assert result['WELLSPRING_MAP_TILE_DIR']=='E:/synthetic tiles'
    assert result['WELLSPRING_MAP_TILE_CRS']=='GCJ02' and result['WELLSPRING_MAP_MAX_ZOOM']=='15'
    assert result['WELLSPRING_MAP_CENTER']=='120.06,31.55' and result['WELLSPRING_MAP_INITIAL_ZOOM']=='11'
