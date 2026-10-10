"""Run original smoke/API with fresh schema, no real DB or delivery credentials."""
import argparse
import ast
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def fixture():
    # Do not copy delivery/provider keys, PG defaults, service files or real DSNs.
    env = {k: v for k, v in os.environ.items()
           if k in {"PATH", "HOME", "LANG", "LC_ALL", "PYTHONHOME", "PYTHONUSERBASE",
                    "LD_LIBRARY_PATH", "NIX_LD", "NIX_LD_LIBRARY_PATH"}}
    proc = None
    with tempfile.TemporaryDirectory(prefix="homenstay-legacy-pg-") as name:
        root = Path(name)
        sock = root / "socket"
        sock.mkdir(mode=0o700)
        (sock / ".owned").write_text("owned ephemeral legacy fixture")
        with (root / "postgres.log").open("w") as output:
            try:
                initdb, postgres = shutil.which("initdb"), shutil.which("postgres")
                if not initdb or not postgres:
                    raise RuntimeError("Local PostgreSQL missing; no external fallback")
                subprocess.run([initdb, "-D", str(root / "data"), "-U", "legacy_fixture",
                                "--auth-local=trust", "--auth-host=reject", "--no-locale",
                                "-E", "UTF8"], env=env, stdout=output,
                               stderr=subprocess.STDOUT, check=True, timeout=30)
                proc = subprocess.Popen(
                    [postgres, "-D", str(root / "data"), "-h", "", "-k", str(sock),
                     "-p", "55438"], env=env, stdout=output,
                    stderr=subprocess.STDOUT, start_new_session=True)
                deadline = time.monotonic() + 15
                while not (sock / ".s.PGSQL.55438").exists():
                    if proc.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError("Owned PostgreSQL startup failed")
                    time.sleep(.05)
                env.update(
                    HOMENSTAY_LEGACY_SOCKET=str(sock),
                    DATABASE_URL=f"postgresql://legacy_fixture@/postgres?host={sock}&port=55438&sslmode=disable",
                    DISABLE_EXTERNAL_NOTIFICATIONS="1", SKIP_APP_BOOT_TASKS="1",
                    SKIP_STARTUP_SCHEMA_INIT="0", FLASK_SECRET_KEY="owned-legacy-test-only",
                    KAKAO_JS_KEY="owned-test-sdk-placeholder",
                    HOMENSTAY_OFFLINE_TESTS="1",
                    PYTHONPATH=str(ROOT / "tests" / "owned_legacy_guard") + ":" + str(ROOT),
                    NODE_OPTIONS="--require=" + str(ROOT / "tests" / "offline_support" / "browser_guard.cjs"))
                work = root / "workspace"
                work.mkdir()
                for entry in ROOT.iterdir():
                    if entry.name not in {".local", ".git", "법정동코드 전체자료.csv"}:
                        (work / entry.name).symlink_to(entry, target_is_directory=entry.is_dir())
                (work / "법정동코드 전체자료.csv").write_text(
                    "법정동코드\t법정동명\t폐지여부\n"
                    "4115000000\t경기도 의정부시\t존재\n"
                    "4115010100\t경기도 의정부시 의정부동\t존재\n",
                    encoding="cp949")
                env["HOMENSTAY_LEGACY_WORKSPACE"] = str(work)
                env["KAKAO_REST_API_KEY"] = "owned-test-placeholder"
                yield env
            finally:
                if proc and proc.poll() is None:
                    proc.send_signal(signal.SIGTERM)
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                print("Owned legacy PostgreSQL stopped and temporary data deleted.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", choices=["smoke", "api"])
    args = parser.parse_args()
    child = None
    with fixture() as env:
        try:
            # The frozen initializer assumes an existing legacy schema (some
            # ALTERs precede CREATEs). Seed exact original literal CREATEs in
            # dependency order, not live rows, before importing that initializer.
            tree = ast.parse((ROOT / "db.py").read_text())
            prerequisite = [node.args[0].value for node in ast.walk(tree)
                            if isinstance(node, ast.Call) and node.args
                            and isinstance(node.args[0], ast.Constant)
                            and isinstance(node.args[0].value, str)
                            and node.args[0].value.lstrip().startswith(
                                "CREATE TABLE IF NOT EXISTS ")]
            setup = """import os,psycopg2
c=psycopg2.connect(os.environ['DATABASE_URL'])
q=c.cursor()
remaining=DDL
while remaining:
    pending=[]
    for sql in remaining:
        q.execute('SAVEPOINT prerequisite')
        try:
            q.execute(sql)
        except psycopg2.errors.UndefinedTable:
            q.execute('ROLLBACK TO SAVEPOINT prerequisite')
            pending.append(sql)
        q.execute('RELEASE SAVEPOINT prerequisite')
    if len(pending)==len(remaining):
        raise RuntimeError('Legacy schema prerequisite dependency cycle')
    remaining=pending
c.commit()
print('Owned legacy schema prerequisites created; zero live rows copied.')
import db
db.init_db()
q=c.cursor()
q.executemany(
    "INSERT INTO master_buildings(building_name,road_address,jibun_address,"
    "sgg_text,sgg_cd,umd_nm,jibun,units,lodging_type,lat,lng) "
    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
    [(f'가상 검증 건물 {i}',f'경기도 의정부시 가상검증로 {i}',
      f'경기도 의정부시 의정부동 {9000+i}', '경기도 의정부시',
      '41150','의정부동',str(9000+i),20,'생활',
      37.5 if i<35 else 35.16,127.05 if i<35 else 129.05) for i in range(40)])
c.commit()
c.close()
print('Forty synthetic master buildings seeded; no real property rows copied.')
""".replace("remaining=DDL", f"remaining={prerequisite!r}")
            prepared = subprocess.run([sys.executable, "-c", setup], cwd=ROOT, env=env,
                                      timeout=60)
            if prepared.returncode:
                raise RuntimeError("Owned legacy schema/fixture bootstrap failed")
            child = subprocess.Popen(
                [sys.executable, str(ROOT / "tests" / (args.suite + "_test.py"))],
                cwd=env["HOMENSTAY_LEGACY_WORKSPACE"], env=env, start_new_session=True)
            return child.wait(timeout=600)
        finally:
            if child:
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()


if __name__ == "__main__":
    sys.exit(main())
