#!/usr/bin/env python3
"""Opt-in Linux image rehearsal with disposable PostgreSQL/PostGIS only.

Never imports host application code, reads .env, accepts a database URL, mounts
host data, publishes ports, contacts Azure, or uploads an image. It requires both
images to exist locally. Only labelled containers/network created by this run
are removed. Database storage is tmpfs, with random throwaway credentials.
"""

import argparse
import base64
import json
import os
import secrets
import subprocess
import sys
import time
import uuid
from urllib.parse import quote


LABEL = "com.geovision.isolated-pilot-test"


class Rehearsal:
    def __init__(self, image, postgres_image):
        self.image = image
        self.postgres_image = postgres_image
        self.run_id = uuid.uuid4().hex
        self.network = "gv-pilot-check-" + self.run_id[:12]
        self.postgres = self.network + "-db"
        self.api = self.network + "-api"
        self.containers = []
        self.network_created = False
        # Exercise real DSN escaping and Alembic ConfigParser interpolation:
        # token_urlsafe alone never exposed failures caused by percent escapes.
        password = secrets.token_urlsafe(32) + "% ! @ : /"
        encoded_password = quote(password, safe="")
        self.private_values = [password, encoded_password, encoded_password.replace("%", "%%")]
        self.env = {
            "ENV": "staging", "PORT": "8010",
            "DATABASE_URL": "postgresql://fixture:" + encoded_password + "@db:5432/geovision",
            "ACCOUNTS_DATABASE_URL": "postgresql://fixture:" + encoded_password + "@db:5432/geovision_accounts",
            "SECRET_KEY": secrets.token_urlsafe(48),
            "ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
            "FRONTEND_BASE": "https://frontend.example.invalid",
            "BACKEND_BASE": "https://api.example.invalid",
            "CORS_ORIGINS": "https://frontend.example.invalid",
            "RUN_MIGRATIONS_ON_STARTUP": "false",
            "STARTUP_COMPATIBILITY_BOOTSTRAP": "false",
            "READINESS_REQUIRE_CURRENT_SCHEMA": "true",
            "MIGRATE_TIMEOUT_SECONDS": "240",
            "QUEUE_PROVIDER": "database", "EVENT_WORKER_IN_PROCESS": "false",
            "ERP_PROVIDER": "mock", "NOTIFICATION_PROVIDER": "none",
            "OBJECT_STORAGE_PROVIDER": "local", "OBSERVABILITY_EXPORTER": "console",
            "PROCESSING_WORKER_IN_PROCESS": "false", "INTELLIGENCE_WORKER_IN_PROCESS": "false",
            "IOT_WATCHDOG_IN_PROCESS": "false", "MQTT_ENABLED": "false",
        }
        self.private_values.extend([self.env["SECRET_KEY"], self.env["ENCRYPTION_KEY"]])
        self.pg_env = {"POSTGRES_USER": "fixture", "POSTGRES_PASSWORD": password, "POSTGRES_DB": "geovision"}

    def docker(self, args, *, input_text=None, env=None, check=True, timeout=300):
        result = subprocess.run(
            ["docker"] + list(args), input=input_text, text=True,
            capture_output=True, env={**os.environ, **(env or {})}, timeout=timeout,
        )
        if check and result.returncode:
            detail = (result.stdout + result.stderr)[-4000:]
            for value in self.private_values:
                detail = detail.replace(value, "[throwaway-value-redacted]")
            raise RuntimeError("Disposable container check failed: " + detail)
        return result

    @staticmethod
    def env_args(env):
        return [argument for name in env for argument in ("--env", name)]

    def create(self, name, image, command, *, env=None, extra=None, read_only=True):
        args = ["create", "--pull", "never", "--platform", "linux/amd64",
                "--name", name, "--label", LABEL + "=" + self.run_id,
                "--network", self.network, "--memory", "1g", "--cpus", "1"]
        if read_only:
            args += ["--read-only", "--tmpfs", "/tmp:rw,nosuid,nodev,size=128m",
                     "--tmpfs", "/runtime:rw,nosuid,nodev,size=64m,uid=10001,gid=10001",
                     "--cap-drop", "ALL", "--security-opt", "no-new-privileges"]
        args += self.env_args(env or {}) + (extra or []) + [image] + command
        self.containers.append(name)
        self.docker(args, env=env)

    def one_shot(self, command, *, env=None):
        name = self.network + "-job-" + str(len(self.containers))
        self.create(name, self.image, command, env=self.env if env is None else env)
        self.docker(["start", "--attach", name])
        exit_code = self.docker(["inspect", "--format", "{{.State.ExitCode}}", name]).stdout.strip()
        if exit_code != "0":
            logs = self.docker(["logs", "--tail", "40", name]).stdout
            for value in self.private_values:
                logs = logs.replace(value, "[throwaway-value-redacted]")
            raise RuntimeError("Disposable job exited " + exit_code + ": " + logs)

    def sql(self, database, statement):
        return self.docker(["exec", "-i", self.postgres, "psql", "-U", "fixture", "-d", database,
                            "-X", "-v", "ON_ERROR_STOP=1", "-t", "-A"], input_text=statement).stdout.strip()

    def request(self, path):
        script = """import json, urllib.request, urllib.error
try:
    with urllib.request.urlopen('http://127.0.0.1:8010' + %r, timeout=5) as response:
        print(json.dumps({'status': response.status, 'body': json.loads(response.read())}))
except urllib.error.HTTPError as error:
    print(json.dumps({'status': error.code, 'body': json.loads(error.read())}))
""" % path
        return json.loads(self.docker(["exec", self.api, "python", "-c", script]).stdout)

    def wait_for_process(self):
        # PostGIS extension initialization is slower under amd64 emulation.
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            result = self.docker(["exec", self.postgres, "pg_isready", "-h", "127.0.0.1", "-U", "fixture", "-d", "geovision"], check=False)
            if result.returncode == 0:
                return
            time.sleep(1)
        raise RuntimeError("Disposable PostgreSQL did not become ready.")

    def run(self):
        pinned_images = []
        for image in (self.image, self.postgres_image):
            architecture = self.docker(["image", "inspect", "--format", "{{.Architecture}}", image]).stdout.strip()
            if architecture != "amd64":
                raise RuntimeError("A local linux/amd64 image is required: " + image)
            pinned_images.append(self.docker(["image", "inspect", "--format", "{{.Id}}", image]).stdout.strip())
        self.image, self.postgres_image = pinned_images
        print("Testing immutable local image: " + self.image, flush=True)
        self.network_created = True
        self.docker(["network", "create", "--internal", "--label", LABEL + "=" + self.run_id, self.network])
        self.one_shot(["python", "-c", """from pathlib import Path
import os
root = Path('/app')
assert os.getuid() == 10001
required = ['start.py','alembic.ini','accounts_alembic.ini','alembic/env.py','accounts_alembic/env.py','accounts_alembic/versions/accounts_v1.py']
assert all((root / path).is_file() for path in required)
allowed = {'Dockerfile','requirements.deploy.txt','start.py','alembic.ini','accounts_alembic.ini','alembic/script.py.mako'}
for path in root.rglob('*'):
    if not path.is_file():
        continue
    relative = path.relative_to(root).as_posix()
    assert not path.is_symlink(), 'unexpected symbolic link in application context'
    assert relative in allowed or (relative.startswith(('app/','alembic/','accounts_alembic/')) and relative.endswith('.py')), relative
    assert not any(part in {'uploads','credentials','backups','__pycache__'} or part.startswith('.env') for part in path.parts), relative
print('Source-only package and non-root runtime verified.')
"""])
        print("PASS: built image contains only permitted runtime sources and runs as UID10001", flush=True)
        self.one_shot(["python", "-m", "pip", "check"])
        print("PASS: installed runtime dependency metadata is consistent", flush=True)

        self.create(self.postgres, self.postgres_image, [], env=self.pg_env, read_only=False,
                    extra=["--network-alias", "db", "--tmpfs", "/var/lib/postgresql/data:rw,nosuid,nodev,size=512m"])
        self.docker(["start", self.postgres])
        self.wait_for_process()
        self.sql("postgres", "CREATE DATABASE geovision_accounts; CREATE DATABASE geovision_legacy;")
        assert self.sql("geovision", "SELECT extname FROM pg_extension WHERE extname='postgis';") == "postgis"
        print("PASS: fresh PostgreSQL/PostGIS, isolated internal network and tmpfs; no host ports or data mounts", flush=True)

        self.one_shot(["python", "start.py", "migrate"])
        primary_head = self.sql("geovision", "SELECT version_num FROM alembic_version;")
        assert primary_head
        assert self.sql("geovision_accounts", "SELECT version_num FROM alembic_version;") == "accounts_v1"
        assert self.sql("geovision", "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name='customer_accounts';") == "0"
        self.sql("geovision_accounts", "INSERT INTO customer_accounts(name,email,created_at) VALUES ('Synthetic fixture','fixture@example.invalid',CURRENT_TIMESTAMP);")
        self.one_shot(["python", "start.py", "migrate"])
        assert self.sql("geovision_accounts", "SELECT count(*) FROM customer_accounts;") == "1"
        assert self.sql("geovision", "SELECT version_num FROM alembic_version;") == primary_head
        assert self.sql("geovision", "SELECT count(*) FROM users;") == "0"
        print("PASS: primary and accounts migration jobs complete twice; separate accounts DB preserves its synthetic row", flush=True)

        self.one_shot(["python", "-c", """import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from app.core.readiness import assert_accounts_database_ready
engine = create_engine(os.environ['ACCOUNTS_DATABASE_URL'])
assert_accounts_database_ready(engine)
assert set(inspect(engine).get_table_names()) == {'alembic_version','customer_accounts','employees'}
with engine.begin() as connection:
    for table, values in [('customer_accounts', "('Duplicate','fixture@example.invalid',CURRENT_TIMESTAMP)"), ('employees', "('Worker','worker@example.invalid','analyst',CURRENT_TIMESTAMP)")]:
        if table == 'employees':
            connection.execute(text("INSERT INTO employees(name,email,role,created_at) VALUES " + values))
        try:
            with connection.begin_nested():
                columns = 'name,email,role,created_at' if table == 'employees' else 'name,email,created_at'
                connection.execute(text('INSERT INTO ' + table + '(' + columns + ') VALUES ' + values))
        except IntegrityError:
            pass
        else:
            raise AssertionError('Email uniqueness was not enforced: ' + table)
engine.dispose()
"""])
        print("PASS: PostgreSQL accounts head readiness and both unique-email constraints", flush=True)

        self.sql("geovision_legacy", "CREATE TABLE customer_accounts(id integer PRIMARY KEY, original text); INSERT INTO customer_accounts VALUES(1,'preserve');")
        legacy_env = {**self.env, "ACCOUNTS_DATABASE_URL": self.env["ACCOUNTS_DATABASE_URL"].replace("/geovision_accounts", "/geovision_legacy")}
        self.one_shot(["python", "-c", """import os
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError
try:
    command.upgrade(Config('accounts_alembic.ini'), 'head')
except ProgrammingError as error:
    assert getattr(error.orig, 'pgcode', None) == '42P07', 'expected duplicate-table rejection'
    engine = create_engine(os.environ['ACCOUNTS_DATABASE_URL'])
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT original FROM customer_accounts WHERE id=1')) == 'preserve'
    engine.dispose()
else:
    raise AssertionError('Unversioned legacy tables were silently adopted')
"""], env=legacy_env)
        print("PASS: unversioned accounts database rejected without overwriting its synthetic existing record", flush=True)

        before_start = self.sql("geovision_accounts", "SELECT count(*) FROM customer_accounts;")
        self.create(self.api, self.image, ["python", "start.py", "serve", "--skip-migrations"], env=self.env)
        self.docker(["start", self.api])
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                if self.request("/health")["status"] == 200:
                    break
            except (RuntimeError, json.JSONDecodeError):
                pass
            time.sleep(1)
        else:
            logs = self.docker(["logs", "--tail", "35", self.api], check=False)
            detail = (logs.stdout + logs.stderr)[-4000:]
            for value in self.private_values:
                detail = detail.replace(value, "[throwaway-value-redacted]")
            raise RuntimeError("API did not start on the disposable database: " + detail)
        assert self.request("/ready") == {"status": 200, "body": {"status": "ready"}}
        assert self.sql("geovision_accounts", "SELECT count(*) FROM customer_accounts;") == before_start
        self.sql("geovision_accounts", "UPDATE alembic_version SET version_num='isolated_wrong_head';")
        assert self.request("/health")["status"] == 200
        assert self.request("/ready") == {"status": 503, "body": {"detail": "service unavailable"}}
        self.sql("geovision_accounts", "UPDATE alembic_version SET version_num='accounts_v1';")
        assert self.request("/ready")["status"] == 200
        self.sql("geovision", "UPDATE alembic_version SET version_num='isolated_wrong_head';")
        assert self.request("/ready") == {"status": 503, "body": {"detail": "service unavailable"}}
        # primary_head came exclusively from this just-created disposable database.
        assert primary_head.replace('_', '').isalnum()
        self.sql("geovision", "UPDATE alembic_version SET version_num='" + primary_head + "';")
        assert self.request("/ready")["status"] == 200
        print("PASS: strict staging HTTP readiness validates BOTH database heads, fails503 safely and recovers; health stays200", flush=True)
        self.docker(["stop", "--time", "15", self.api])
        assert self.docker(["inspect", "--format", "{{.State.ExitCode}}", self.api]).stdout.strip() == "0"
        print("PASS: read-only non-root API gracefully stops; no cloud/provider integration claim", flush=True)

    def cleanup(self):
        failures = []
        for name in reversed(self.containers):
            result = self.docker(["inspect", "--format", '{{index .Config.Labels "' + LABEL + '"}}', name], check=False)
            if result.returncode == 0 and result.stdout.strip() == self.run_id:
                if self.docker(["rm", "--force", "--volumes", name], check=False).returncode:
                    failures.append(name)
            elif result.returncode == 0:
                failures.append(name + " (label mismatch; not touched)")
            elif "No such" not in result.stderr:
                failures.append(name + " (could not verify)")
        if self.network_created:
            result = self.docker(["network", "inspect", "--format", '{{index .Labels "' + LABEL + '"}}', self.network], check=False)
            if result.returncode == 0 and result.stdout.strip() == self.run_id:
                if self.docker(["network", "rm", self.network], check=False).returncode:
                    failures.append(self.network)
            elif result.returncode == 0:
                failures.append(self.network + " (label mismatch; not touched)")
            elif "not found" not in result.stderr and "No such" not in result.stderr:
                failures.append(self.network + " (could not verify)")
        if failures:
            raise RuntimeError("Cleanup incomplete for this run only: " + ", ".join(failures))
        print("Disposable rehearsal resources cleaned up; existing containers/data were not targeted.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="geovision-backend:azure-pilot-20260912")
    parser.add_argument("--postgres-image", default="postgis/postgis:16-3.5")
    args = parser.parse_args()
    rehearsal = Rehearsal(args.image, args.postgres_image)
    try:
        rehearsal.run()
    finally:
        rehearsal.cleanup()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
