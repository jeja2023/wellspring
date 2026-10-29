#!/bin/sh
set -eu
export APP_RUNTIME_PASSWORD="$(cat /run/secrets/runtime_password)"
psql --set ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
\getenv app_role_password APP_RUNTIME_PASSWORD
SELECT format('CREATE ROLE wellspring_app LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS', :'app_role_password') \gexec
GRANT CONNECT ON DATABASE wellspring TO wellspring_app;
GRANT USAGE ON SCHEMA public TO wellspring_app;
ALTER DEFAULT PRIVILEGES FOR ROLE wellspring_owner IN SCHEMA public GRANT SELECT, INSERT, UPDATE ON TABLES TO wellspring_app;
ALTER DEFAULT PRIVILEGES FOR ROLE wellspring_owner IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO wellspring_app;
SQL
unset APP_RUNTIME_PASSWORD
