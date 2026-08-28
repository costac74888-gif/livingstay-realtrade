# -*- coding: utf-8 -*-
"""
db.py — SQLite 초기화 및 공용 DB 함수

테이블 구성
------------------------------------------------------------
master_buildings : 첨부 마스터파일(전국 생숙 현황) 원본을 그대로 적재
                    → 건물명 확정의 "정답지" 역할
transactions     : 배치 수집으로 쌓이는 실거래 (매매) 데이터
                    → 게시판/검색 화면이 읽는 테이블
sync_log         : 배치 실행 이력 (언제, 몇 건, 성공/실패)
"""

# -*- coding: utf-8 -*-
"""
db.py — PostgreSQL(Replit 제공 DB) 초기화 및 공용 DB 함수

Replit에서 왼쪽 메뉴 "Database" 탭 → "Create a database" (Postgres) 를 누르면
DATABASE_URL 환경변수(Secret)가 자동으로 주입됩니다. 이 파일은 그 환경변수를 읽어서 접속합니다.

테이블 구성
------------------------------------------------------------
master_buildings : 첨부 마스터파일(전국 생숙 현황) 원본을 그대로 적재
                    → 건물명 확정의 "정답지" 역할
transactions     : 배치 수집으로 쌓이는 실거래 (매매) 데이터
                    → 게시판/검색 화면이 읽는 테이블
sync_log         : 배치 실행 이력 (언제, 몇 건, 성공/실패)
"""

import atexit
import logging
import os
import threading
from contextlib import contextmanager
import psycopg2
import psycopg2.extras
from psycopg2.pool import PoolError, ThreadedConnectionPool
from werkzeug.security import generate_password_hash


_logger = logging.getLogger(__name__)
_POOL_MIN_CONNECTIONS = 2
_POOL_MAX_CONNECTIONS = 20
_POOL_RESERVED_FOR_REQUESTS = 1
_BACKGROUND_POOL_MAX_CONNECTIONS = 2
_connection_pool = None
_connection_pool_pid = None
_borrowed_connections = {}
_connection_pool_lock = threading.RLock()
_background_connection_slots = None
_background_connection_slot_limit = 0
_connection_priority = threading.local()


class _PooledConnection:
    """기존 conn.close() 호출을 안전한 풀 반환으로 연결하는 호환 래퍼.

    프로젝트에 오래된 배치가 많아 전부를 동시에 바꾸는 동안에도 물리 연결을 닫거나
    반환을 빼먹지 않게 한다. 새 코드는 release_conn()/connection()을 명시적으로 쓴다.
    """

    def __init__(self, raw_connection):
        object.__setattr__(self, "_raw_connection", raw_connection)
        object.__setattr__(self, "_released", False)
        object.__setattr__(self, "_lease_token", object())
        object.__setattr__(self, "_background_slot", None)

    def __getattr__(self, name):
        return getattr(self._raw_connection, name)

    def __setattr__(self, name, value):
        if name in {"_raw_connection", "_released", "_lease_token", "_background_slot"}:
            object.__setattr__(self, name, value)
        else:
            setattr(self._raw_connection, name, value)

    def __enter__(self):
        self._raw_connection.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return self._raw_connection.__exit__(exc_type, exc_value, traceback)

    def close(self):
        """기존 호출부 호환용: 물리 close 대신 풀로 반환한다."""
        release_conn(self)

    def __del__(self):
        # 구형 배치의 예외 경로를 위한 보조 안전망. release_conn은 대여 토큰까지
        # 일치할 때만 반환하므로, 같은 원시 연결이 재대여된 뒤에는 건드리지 않는다.
        try:
            release_conn(self)
        except Exception:
            pass


def _reset_connection_pool_after_fork():
    """fork된 자식은 부모의 DB 소켓과 잠금 객체를 절대 이어받지 않는다."""
    global _connection_pool, _connection_pool_pid, _borrowed_connections
    global _connection_pool_lock, _background_connection_slots
    global _background_connection_slot_limit
    _connection_pool = None
    _connection_pool_pid = None
    _borrowed_connections = {}
    _connection_pool_lock = threading.RLock()
    _background_connection_slots = None
    _background_connection_slot_limit = 0


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_connection_pool_after_fork)


def _pool_size_from_env(name, default):
    """잘못된 환경 설정 하나가 앱 기동을 막지 않게 양수만 반영한다."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        _logger.warning("DB 풀 설정 %s=%r이 올바른 정수가 아니어서 기본값 %s을 사용합니다.", name, raw, default)
        return default
    if value < 1:
        _logger.warning("DB 풀 설정 %s=%r은 1 이상이어야 하므로 기본값 %s을 사용합니다.", name, raw, default)
        return default
    return value

def _background_pool_size_from_env():
    """백그라운드용 동시 연결 상한을 읽는다. 0은 의도적인 비활성 값이다."""
    raw = os.environ.get(
        "DB_POOL_BACKGROUND_MAXCONN",
        str(_BACKGROUND_POOL_MAX_CONNECTIONS),
    )
    try:
        value = int(raw)
    except ValueError:
        _logger.warning(
            "DB_POOL_BACKGROUND_MAXCONN=%r이 올바른 정수가 아니어서 기본값 %s을 사용합니다.",
            raw,
            _BACKGROUND_POOL_MAX_CONNECTIONS,
        )
        return _BACKGROUND_POOL_MAX_CONNECTIONS
    if value < 0:
        _logger.warning(
            "DB_POOL_BACKGROUND_MAXCONN=%r은 0 이상이어야 하므로 기본값 %s을 사용합니다.",
            raw,
            _BACKGROUND_POOL_MAX_CONNECTIONS,
        )
        return _BACKGROUND_POOL_MAX_CONNECTIONS
    return value
def _get_connection_pool():
    """현재 프로세스 전용 풀을 반환한다.

    gunicorn pre-load/fork 뒤 부모 프로세스의 소켓을 자식이 재사용하면 안 된다.
    PID가 바뀐 경우 상속된 풀은 closeall()하지 않고 버리고, 자식에서 새로 만든다.
    """
    global _connection_pool, _connection_pool_pid
    global _background_connection_slots, _background_connection_slot_limit
    current_pid = os.getpid()

    with _connection_pool_lock:
        if _connection_pool is not None and _connection_pool_pid == current_pid:
            return _connection_pool

        if _connection_pool is not None:
            if _connection_pool_pid == current_pid:
                # 이 경로는 현재 없지만, 향후 명시 재설정 시 누수를 막는다.
                try:
                    _connection_pool.closeall()
                except Exception:
                    _logger.warning("기존 DB 연결 풀 종료 실패", exc_info=True)
            else:
                # fork된 자식에서 부모 연결을 닫으면 부모 세션까지 끊길 수 있다.
                _logger.warning(
                    "DB 연결 풀이 다른 PID(%s)에서 상속되어 폐기합니다; 새 풀을 생성합니다.",
                    _connection_pool_pid,
                )
            _connection_pool = None
            _connection_pool_pid = None
            _borrowed_connections.clear()

        minconn = _pool_size_from_env("DB_POOL_MINCONN", _POOL_MIN_CONNECTIONS)
        maxconn = _pool_size_from_env("DB_POOL_MAXCONN", _POOL_MAX_CONNECTIONS)
        if maxconn < minconn:
            _logger.warning(
                "DB_POOL_MAXCONN(%s)이 DB_POOL_MINCONN(%s)보다 작아 minconn 값으로 올립니다.",
                maxconn,
                minconn,
            )
            maxconn = minconn

        database_url = os.environ["DATABASE_URL"]
        _connection_pool = ThreadedConnectionPool(
            minconn=minconn,
            maxconn=maxconn,
            dsn=database_url,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
        # 저우선순위 작업은 사용자 요청용 연결 하나를 반드시 남긴다.
        background_limit = min(
            _background_pool_size_from_env(),
            max(0, maxconn - _POOL_RESERVED_FOR_REQUESTS),
        )
        _background_connection_slots = threading.BoundedSemaphore(background_limit)
        _background_connection_slot_limit = background_limit
        _connection_pool_pid = current_pid
        _logger.info(
            "DB 연결 풀 생성 완료 (pid=%s, min=%s, max=%s, background_max=%s)",
            current_pid,
            minconn,
            maxconn,
            background_limit,
        )
        return _connection_pool


def get_conn():
    """
    현재 프로세스의 PostgreSQL 연결 풀에서 연결 하나를 대여한다.
    반드시 release_conn()으로 반환해야 한다.
    """
    pool = _get_connection_pool()
    background = bool(getattr(_connection_priority, "background", False))
    background_slot = None
    if background:
        with _connection_pool_lock:
            background_slot = _background_connection_slots
        if background_slot is None or not background_slot.acquire(blocking=False):
            raise BackgroundConnectionUnavailable(
                "사용자 요청용 DB 연결을 남기기 위해 백그라운드 작업을 다음 주기로 미룹니다."
            )

    try:
        raw_connection = pool.getconn()
    except PoolError:
        _release_background_slot(background_slot)
        if background:
            raise BackgroundConnectionUnavailable(
                "DB 연결 풀이 사용 중이어서 백그라운드 작업을 다음 주기로 미룹니다."
            )
        _logger.error(
            "DB 연결 풀이 고갈되었습니다 (pid=%s). DB_POOL_MAXCONN 또는 동시 작업을 확인하세요.",
            os.getpid(),
            exc_info=True,
        )
        raise
    except Exception:
        _release_background_slot(background_slot)
        _logger.error("DB 연결 풀에서 연결 대여 실패", exc_info=True)
        raise

    conn = _PooledConnection(raw_connection)
    conn._background_slot = background_slot
    with _connection_pool_lock:
        _borrowed_connections[id(raw_connection)] = (pool, os.getpid(), conn._lease_token)
    _track_request_connection(conn)
    return conn


def release_conn(conn):
    """대여한 연결을 정리한 뒤 원래 풀로 반환한다.

    커밋하지 않은 SELECT/쓰기나 오류 난 트랜잭션은 항상 rollback한다. 반환 전 정리에
    실패하거나 이미 닫힌 연결은 풀에서 제거해 다음 요청에 재사용되지 않게 한다.
    """
    if conn is None:
        return

    if isinstance(conn, _PooledConnection):
        if conn._released:
            return
        object.__setattr__(conn, "_released", True)
        raw_connection = conn._raw_connection
        lease_token = conn._lease_token
        background_slot = conn._background_slot
    else:
        raw_connection = conn
        lease_token = None
        background_slot = None

    with _connection_pool_lock:
        borrowed = _borrowed_connections.get(id(raw_connection))
        if isinstance(conn, _PooledConnection):
            # 오래된 래퍼가 GC된 시점에는 같은 원시 연결이 이미 다른 요청에
            # 재대여됐을 수 있다. 그 경우 새 대여분은 절대 반환하거나 rollback하지 않는다.
            if borrowed is None or borrowed[2] is not lease_token:
                _release_background_slot(background_slot)
                return
        borrowed = _borrowed_connections.pop(id(raw_connection), None)

    if borrowed is None:
        # database_url 인자를 받은 별도 접속 등, 풀 바깥 연결도 이 함수로 안전하게 닫을 수 있다.
        try:
            raw_connection.close()
        except Exception:
            _logger.warning("미등록 DB 연결 폐기 실패", exc_info=True)
        _release_background_slot(background_slot)
        return

    pool, borrowed_pid, _ = borrowed
    if borrowed_pid != os.getpid():
        _logger.warning("다른 PID에서 대여한 DB 연결 반환 요청 — 연결을 폐기합니다.")
        try:
            raw_connection.close()
        except Exception:
            _logger.warning("fork 후 상속된 DB 연결 폐기 실패", exc_info=True)
        _release_background_slot(background_slot)
        return

    discard = bool(getattr(raw_connection, "closed", True))
    try:
        if not discard:
            # CONCURRENTLY DDL 등 일부 호출부는 autocommit을 켠다. 이 상태를 그대로
            # 재사용하면 다음 요청의 다중 쓰기가 트랜잭션 밖에서 실행될 수 있다.
            if raw_connection.autocommit:
                raw_connection.autocommit = False
            # IDLE 상태에서도 rollback은 안전하며, 열린 트랜잭션을 다음 요청으로 넘기지 않는다.
            raw_connection.rollback()
    except Exception:
        discard = True
        _logger.warning("DB 연결 반환 전 rollback 실패 — 연결을 폐기합니다.", exc_info=True)

    try:
        pool.putconn(raw_connection, close=discard)
        if discard:
            _logger.warning("닫혔거나 오류 난 DB 연결을 풀에서 폐기했습니다.")
    except Exception:
        _logger.error("DB 연결 풀 반환 실패 — 연결을 폐기합니다.", exc_info=True)
        try:
            raw_connection.close()
        except Exception:
            pass
    finally:
        _release_background_slot(background_slot)


@contextmanager
def connection():
    """새 코드에서 누수를 막기 위한 공용 연결 컨텍스트 관리자."""
    conn = get_conn()
    try:
        yield conn
    finally:
        release_conn(conn)


def _track_request_connection(conn):
    """Flask 요청 안에서 빌린 연결은 teardown에서 결정적으로 반환한다."""
    try:
        from flask import g, has_request_context
        if not has_request_context():
            return
        tracked = getattr(g, "_pooled_db_connections", None)
        if tracked is None:
            tracked = []
            g._pooled_db_connections = tracked
        tracked.append(conn)
    except (ImportError, RuntimeError):
        # 배치·CLI에서는 Flask 컨텍스트가 없으며 호출부의 close/finalizer가 처리한다.
        return


def release_request_connections():
    """요청 중 예외로 누락된 legacy conn.close()를 teardown에서 회수한다."""
    try:
        from flask import g, has_request_context
        if not has_request_context():
            return
        tracked = getattr(g, "_pooled_db_connections", [])
        g._pooled_db_connections = []
    except (ImportError, RuntimeError):
        return

    for conn in reversed(tracked):
        release_conn(conn)


def close_connection_pool():
    """현재 프로세스의 풀을 종료한다. 정상 종료 훅과 테스트 정리에 사용한다."""
    global _connection_pool, _connection_pool_pid
    with _connection_pool_lock:
        pool = _connection_pool
        pool_pid = _connection_pool_pid
        _connection_pool = None
        _connection_pool_pid = None
        _borrowed_connections.clear()

    if pool is None:
        return
    if pool_pid != os.getpid():
        _logger.warning("다른 PID에서 상속된 DB 풀은 종료하지 않고 폐기합니다.")
        return
    try:
        pool.closeall()
        _logger.info("DB 연결 풀 종료 완료 (pid=%s)", pool_pid)
    except Exception:
        _logger.warning("DB 연결 풀 종료 실패", exc_info=True)


atexit.register(close_connection_pool)


# 스키마 버전 — db.py의 테이블/컬럼/제약을 바꾸면 반드시 이 값을 올려야
# 다음 부팅 때 init_db가 DDL을 다시 실행한다. (값이 같으면 전부 건너뛰어 부팅이 빨라짐)
SCHEMA_VERSION = "2026-08-28-04"
# PostgreSQL 세션 advisory lock 키. 버전 불일치 때만 잡으므로 최신 스키마 부팅은
# DB 잠금 대기 없이 즉시 끝난다. 값은 이 프로젝트의 init_db 전용 고정 식별자다.
_SCHEMA_INIT_ADVISORY_LOCK_KEY = 719_240_391
_SGG_REGION_MIGRATION_KEY = "migration:agent_service_regions:sgg_v1"


def _migrate_agent_regions_to_sgg(cur):
    """동 단위 지역뱃지를 시군구별 한 행으로 병합하고 동 값을 비운다.

    완료 표식을 같은 트랜잭션에서 선점하므로 실패하면 표식도 롤백되고,
    활성·만료 시각이 가장 최신인 행을 보존한다. 담당단지는 중개사 기준
    테이블이므로 행 병합 뒤에도 그대로 유지된다.
    """
    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        INSERT INTO app_meta (key, value, updated_at)
        VALUES (%s, 'completed', NOW())
        ON CONFLICT (key) DO NOTHING
        RETURNING key
    """, (_SGG_REGION_MIGRATION_KEY,))
    if not cur.fetchone():
        return 0, 0
    cur.execute("""
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY agent_id, sgg_text
                       ORDER BY (expires_at > NOW()) DESC, expires_at DESC,
                                granted_at DESC NULLS LAST, id DESC
                   ) AS row_num
            FROM agent_service_regions
        )
        DELETE FROM agent_service_regions sr
        USING ranked r
        WHERE sr.id = r.id AND r.row_num > 1
    """)
    merged_count = cur.rowcount
    cur.execute("""
        UPDATE agent_service_regions
        SET umd_nm = NULL
        WHERE umd_nm IS NOT NULL
    """)
    return merged_count, cur.rowcount


def _schema_version_is_current(conn, cur):
    """app_meta에 현재 스키마 버전이 기록됐는지 확인한다.

    최초 기동처럼 app_meta가 아직 없는 경우에는 PostgreSQL 오류를 롤백하고
    False를 반환해 전체 초기화로 진행한다.
    """
    try:
        cur.execute("SELECT value FROM app_meta WHERE key = 'schema_version'")
        row = cur.fetchone()
        is_current = bool(row and row["value"] == SCHEMA_VERSION)
        # SELECT도 트랜잭션을 열기 때문에, 장시간 초기화 전에 깨끗하게 끝낸다.
        conn.rollback()
        return is_current
    except psycopg2.Error:
        conn.rollback()
        return False


@contextmanager
def _schema_initialization_lock():
    """버전 불일치 시 한 프로세스만 전체 DDL/시드를 실행하게 직렬화한다."""
    conn = get_conn()
    cur = conn.cursor()
    locked = False
    try:
        cur.execute("SELECT pg_advisory_lock(%s)", (_SCHEMA_INIT_ADVISORY_LOCK_KEY,))
        conn.commit()
        locked = True
        yield conn
    finally:
        try:
            if locked:
                cur.execute("SELECT pg_advisory_unlock(%s)", (_SCHEMA_INIT_ADVISORY_LOCK_KEY,))
                conn.commit()
        finally:
            cur.close()
            conn.close()


def init_db():
    """최신 스키마는 즉시 종료하고, 불일치 시에만 직렬화된 전체 초기화를 수행한다."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        if _schema_version_is_current(conn, cur):
            return
    finally:
        cur.close()
        conn.close()

    # 여러 gunicorn 워커가 동시에 부팅해도 한 프로세스만 DDL과 시드를 실행한다.
    # 잠금 대기 중 다른 프로세스가 완료했을 수 있으므로 반드시 다시 확인한다.
    with _schema_initialization_lock() as lock_conn:
        lock_cur = lock_conn.cursor()
        try:
            if _schema_version_is_current(lock_conn, lock_cur):
                return
        finally:
            lock_cur.close()
        _run_init_db()


def _run_init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS master_buildings (
        id SERIAL PRIMARY KEY,
        building_name TEXT NOT NULL,
        road_address TEXT NOT NULL,
        jibun_address TEXT,           -- 도로명→지번 변환 결과 (배치가 채움)
        sgg_text TEXT,                -- "경기도 가평군" 형태
        sgg_cd TEXT,                  -- 법정동코드 앞5자리 (배치가 채움)
        umd_nm TEXT,                  -- 법정동명 (배치가 채움, 매칭 키)
        jibun TEXT,                   -- 지번 (배치가 채움, 매칭 키)
        units INTEGER,                -- 호수(세대수) — 정보용, 필터 기준 아님
        biz_units INTEGER,            -- 레거시 엑셀 스냅샷 참고값(신고율 계산에 사용 금지)
        source TEXT DEFAULT 'original', -- 'original' | 'api_discovered' | 'verify_rescued' | 'sync_verified' | 'user_submitted'
        verified_at TIMESTAMP,         -- is_living_stay로 실검증된 시각 (NULL이면 미검증 → 재분류 대상)
        lodging_type TEXT,             -- '생활'|'관광'|'일반'|'복합' (reclassify가 채움, NULL이면 미분류)
        lodging_type_detail TEXT,      -- 건축물대장 원문 용도 표기 (분류 근거, 화면 배지 툴팁용)
        lodging_subtype TEXT           -- 관광숙박시설 세부유형(관광호텔/호스텔/휴양콘도미니엄 등), 해당없으면 NULL
    )
    """)
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'original'")
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP")
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS lodging_type TEXT")
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS lodging_type_detail TEXT")
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS lodging_subtype TEXT")
    # 기존 '호텔'/'콘도'/병기 데이터를 새 체계로 이관 (lodging_type_detail 원문은 보존).
    cur.execute("""
        UPDATE master_buildings
        SET lodging_type = '관광'
        WHERE lodging_type IN ('호텔', '콘도', '호텔·콘도', '콘도·호텔')
    """)
    # 나머지 '·' 병기(생활·호텔 등)는 복합으로 통합.
    cur.execute("""
        UPDATE master_buildings
        SET lodging_type = '복합'
        WHERE lodging_type LIKE '%·%'
    """)
    # 지도 표시용 좌표 (geocode_buildings.py 가 카카오 주소검색으로 채움, NULL 허용)
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION")
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS lng DOUBLE PRECISION")
    # 정원제 슬롯 최대 정원 (건물당 중개사 노출 좌석 수, 기본 3석)
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS slot_capacity INTEGER DEFAULT 3")
    # 건축물대장 표제부(getBrTitleInfo) 백필값 — backfill_title_info.py가 채운다.
    # 값이 NULL이면 건물 상세 화면에서 "-"로 표시된다.
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS use_apr_day TEXT")        # 사용승인일(준공) YYYY-MM-DD
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS tot_pkng_cnt INTEGER")    # 총주차대수(레거시)
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS indr_auto_utcnt INTEGER")  # 옥내자주식대수
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS oudr_auto_utcnt INTEGER")  # 옥외자주식대수
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS indr_mech_utcnt INTEGER")  # 옥내기계식대수
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS oudr_mech_utcnt INTEGER")  # 옥외기계식대수
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS grnd_flr_cnt INTEGER")    # 지상층수
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS ugrnd_flr_cnt INTEGER")   # 지하층수
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS tot_area DOUBLE PRECISION")  # 연면적(㎡)
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS plat_area DOUBLE PRECISION") # 대지면적(㎡)
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS hhld_cnt INTEGER")        # 세대수
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS strct_nm TEXT")           # 구조
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS title_backfilled_at TIMESTAMP")  # 표제부 백필 시각(재시도/커버리지 추적)
    # building_stores — 호번호/세부업종 추가 (2026-08-16-2)
    cur.execute("ALTER TABLE building_stores ADD COLUMN IF NOT EXISTS ho_no TEXT")           # 호번호(hoNo)
    cur.execute("ALTER TABLE building_stores ADD COLUMN IF NOT EXISTS inds_mcls_nm TEXT")    # 업종 중분류
    cur.execute("ALTER TABLE building_stores ADD COLUMN IF NOT EXISTS inds_scls_nm TEXT")    # 업종 소분류
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS mgm_bldrgst_pk TEXT")    # 관리건축물대장PK(표제부 mgmBldrgstPk. 상가업소 조회 키로는 못 씀 — store_info_util.py 참고)
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS building_status TEXT DEFAULT '완공'")
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS completion_expected_date DATE")
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS permit_day TEXT")        # 건축허가일(YYYYMMDD)
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS actual_start_day TEXT")  # 실제착공일(YYYYMMDD)
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS arch_area DOUBLE PRECISION")  # 건축면적(㎡)
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS bc_rat DOUBLE PRECISION")     # 건폐율(%)
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS vl_rat DOUBLE PRECISION")     # 용적률(%)
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS heit DOUBLE PRECISION")           # 건물높이(m)
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS ride_use_elvt_cnt INTEGER")       # 승용승강기 수
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS emgen_use_elvt_cnt INTEGER")      # 비상승강기 수
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS main_purps_nm TEXT")              # 주용도명
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS jiyuk_nm TEXT")                   # 용도지역명
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS jigu_nm TEXT")                    # 용도지구명
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS guyuk_nm TEXT")                   # 용도구역명
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS last_inspection_agency TEXT")     # 최근 정기점검 기관
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS last_inspection_start_day TEXT")  # 점검시작일 YYYY-MM-DD
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS last_inspection_submit_day TEXT") # 점검제출일 YYYY-MM-DD
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS detail_fetched_at TIMESTAMP")     # 즉시조회 캐싱 시각
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS zip_code TEXT")  # 우편번호 (JUSO API zipNo)
    # 정식 명칭 미확정 표시 — API(건축물대장)에 건물명이 없어 "읍면동 지번" 임시명으로 등록된 건물은 TRUE.
    # 기본값 FALSE: 기존 건물들은 이미 확정된 명칭을 갖고 있으므로, TRUE는 submit_building()이 명시적으로만 세팅한다.
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS name_pending BOOLEAN DEFAULT FALSE")
    # 건물명 출처와 자동 대표 후보 수 — 자동 신고명과 확정 명칭을 API에서 구분한다.
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS building_name_source TEXT DEFAULT 'official'")
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS building_name_candidate_count INTEGER DEFAULT 0")
    # 자동 신고명이 사라졌을 때 되돌릴 원래 임시명. 주소 보조키가 없는 도로명 건물도
    # 대상에서 제외하지 않기 위해 별도로 보존한다.
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS building_name_pending_base TEXT")
    cur.execute("""
        UPDATE master_buildings
           SET building_name_source = 'pending'
         WHERE name_pending IS TRUE
           AND (building_name_source IS NULL OR building_name_source = 'official')
    """)
    cur.execute("""
        UPDATE master_buildings
           SET building_name_pending_base = COALESCE(
                   NULLIF(TRIM(CONCAT_WS(' ', umd_nm, jibun)), ''),
                   NULLIF(jibun_address, ''),
                   NULLIF(road_address, ''),
                   building_name
               )
         WHERE name_pending IS TRUE
           AND building_name_pending_base IS NULL
    """)
    # source_key — 수집 파이프라인별 중복 방지 키 (permit_pipeline: "permit|sgg_cd|bjd_cd|bun|ji").
    # NULL 허용 (기존 행 + 비-permit 소스). 부분 유니크 인덱스로 NULL 행은 제외.
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS source_key TEXT")
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS master_buildings_source_key_uidx
        ON master_buildings (source_key)
        WHERE source_key IS NOT NULL
    """)
    # 1회성 백필(멱등) — 이름이 무의미한 기존 행("(이름 미상)"/"-"/빈값)은 "읍면동 지번"
    # 임시명으로 바꾸고 name_pending=TRUE. 운영 DB에도 배포 부팅 시 자동 적용된다.
    cur.execute("""
        UPDATE master_buildings
        SET building_name = umd_nm || ' ' || jibun, name_pending = TRUE
        WHERE TRIM(COALESCE(building_name, '')) IN ('', '-', '(이름 미상)')
          AND umd_nm IS NOT NULL AND jibun IS NOT NULL
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id SERIAL PRIMARY KEY,
        building_name TEXT,           -- 매칭 성공 시 마스터파일 건물명 (NULL이면 미매칭)
        address TEXT NOT NULL,        -- 법정동 + 지번 조합 표시용 주소
        si_do TEXT,                   -- 시/도 (계층 검색용, 마스터의 sgg_text에서 분리)
        sgg_nm TEXT,                  -- 시/군/구 (계층 검색용)
        area REAL,                    -- 건물면적(㎡)
        price INTEGER,                -- 거래금액(만원)
        deal_date TEXT,               -- 계약년월일 YYYY-MM-DD
        deal_type TEXT,               -- 중개거래 / 직거래
        sgg_cd TEXT,
        umd_nm TEXT,
        jibun TEXT,
        floor TEXT,                   -- 층 (RTMS 응답의 floor 필드, 정보용)
        lodging_type TEXT,            -- '생활' | '호텔' | '콘도' (매칭된 건물 기준, reclassify가 채움)
        lodging_type_detail TEXT,     -- 건축물대장 원문 용도 표기 (배지 툴팁용)
        match_source TEXT,            -- 'master' | 'buildinghub' | 'unmatched'
        raw_key TEXT UNIQUE,          -- 중복 적재 방지용 (sgg_cd+umd_nm+jibun+deal_date+price)
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP
    )
    """)

    # 기존에 이미 만들어진 DB(컬럼 없이 생성됐던 경우)에도 안전하게 컬럼 추가 (데이터 보존)
    cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS si_do TEXT")
    cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS sgg_nm TEXT")
    cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS floor TEXT")
    cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS lodging_type TEXT")
    cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS lodging_type_detail TEXT")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sync_log (
        id SERIAL PRIMARY KEY,
        started_at TIMESTAMP,
        finished_at TIMESTAMP,
        regions_processed INTEGER,
        rows_inserted INTEGER,
        rows_matched_master INTEGER,
        rows_matched_buildinghub INTEGER,
        rows_unmatched INTEGER,
        status TEXT,
        note TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS building_requests (
        id SERIAL PRIMARY KEY,
        road_address TEXT NOT NULL,        -- 사용자가 입력한 도로명주소
        building_name_hint TEXT,           -- 사용자가 적어준 건물명 (참고용)
        requester_note TEXT,               -- 사용자 메모
        status TEXT DEFAULT 'pending',     -- pending | verified | rejected
        reject_reason TEXT,                -- 생숙 아님 / 조회실패 등 사유
        master_building_id INTEGER,        -- 검증 통과 시 편입된 master_buildings.id
        created_at TIMESTAMP DEFAULT NOW(),
        processed_at TIMESTAMP
    )
    """)
    # 용도 정정 요청(correction)까지 지원하도록 컬럼 확장 (기존 DB에도 안전하게 추가)
    cur.execute("ALTER TABLE building_requests ADD COLUMN IF NOT EXISTS request_type TEXT DEFAULT 'new'")   # 'new'(신규 추가) | 'correction'(용도 정정)
    cur.execute("ALTER TABLE building_requests ADD COLUMN IF NOT EXISTS target_sgg_cd TEXT")                # 정정 대상 건물 식별용
    cur.execute("ALTER TABLE building_requests ADD COLUMN IF NOT EXISTS target_umd_nm TEXT")
    cur.execute("ALTER TABLE building_requests ADD COLUMN IF NOT EXISTS target_jibun TEXT")
    cur.execute("ALTER TABLE building_requests ADD COLUMN IF NOT EXISTS suggested_lodging_type TEXT")       # 사용자가 제안한 값 (참고용, 신뢰 안 함)
    cur.execute("ALTER TABLE building_requests ADD COLUMN IF NOT EXISTS verified_lodging_type TEXT")        # 우리가 재검증해 확정한 값
    cur.execute("ALTER TABLE building_requests ADD COLUMN IF NOT EXISTS changed BOOLEAN DEFAULT FALSE")     # 정정 요청 시 실제로 값이 바뀌었는지
    cur.execute("ALTER TABLE building_requests ALTER COLUMN road_address DROP NOT NULL")                    # 정정 요청은 도로명주소가 없으므로
    cur.execute("ALTER TABLE agents ALTER COLUMN reg_number DROP NOT NULL")
    cur.execute("ALTER TABLE building_requests ADD COLUMN IF NOT EXISTS suggested_building_name TEXT")      # 사용자가 제안한 건물명 (API 재조회로 미확인 시 기록만, status='name_review')
    cur.execute("ALTER TABLE building_requests ADD COLUMN IF NOT EXISTS jibun_address_input TEXT")         # 사용자가 직접 입력한 지번주소 원문 (road_to_jibun 우회용)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS admin_users (
        id SERIAL PRIMARY KEY,
        email TEXT NOT NULL,               -- 로그인 아이디 (UNIQUE 제약은 _ensure_admin_email_unique_constraint()에서 안전하게 부여)
        password_hash TEXT NOT NULL,       -- werkzeug generate_password_hash() 결과 (절대 평문 저장 금지)
        name TEXT,                         -- 표시용 이름
        role TEXT DEFAULT 'operator',      -- 'super_admin' | 'operator'
        created_at TIMESTAMP DEFAULT NOW(),
        last_login_at TIMESTAMP            -- 마지막 로그인 시각 (로그인 API가 채움)
    )
    """)
    # 기존에 이미 만들어진 DB에도 안전하게 컬럼 추가 (데이터 보존)
    cur.execute("ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS name TEXT")
    cur.execute("ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'operator'")
    cur.execute("ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()")
    cur.execute("ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS agents (
        id SERIAL PRIMARY KEY,
        office_name TEXT NOT NULL,          -- 중개사무소명
        owner_name TEXT NOT NULL,           -- 대표자명
        reg_number TEXT NOT NULL,           -- 중개사무소 등록번호 (UNIQUE는 _ensure_agents_unique_constraints()에서 안전하게 부여)
        biz_reg_number TEXT,                -- 사업자등록번호
        phone TEXT,
        email TEXT NOT NULL,
        status TEXT DEFAULT 'pending',      -- pending | approved | rejected | suspended
        subdomain_slug TEXT,                -- 승인 시 발급되는 개별페이지 경로 (UNIQUE는 helper에서 부여)
        intro_text TEXT,                    -- 자기소개(선택)
        created_at TIMESTAMP DEFAULT NOW(),
        approved_at TIMESTAMP,
        approved_by INTEGER REFERENCES admin_users(id)   -- 승인한 관리자 (admin_users.id 참조 FK)
    )
    """)
    # 기존에 이미 만들어진 DB에도 안전하게 컬럼 추가 (데이터 보존)
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS biz_reg_number TEXT")
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS phone TEXT")
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending'")
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS subdomain_slug TEXT")
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS intro_text TEXT")
    # 소개글 제목(16자 이내) — 건물상세(B화면) 담당중개사 배너에 노출되는 짧은 문구 (intro_text와 별개)
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS intro_title TEXT")
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()")
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP")
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS approved_by INTEGER REFERENCES admin_users(id)")
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS password_hash TEXT")
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS photo_url TEXT")
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS admin_tag TEXT")  # 관리자 태그(일괄 관리용)
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS logo_url TEXT")  # 파트너 로고(이번엔 스키마만 준비)
    # 노출 여부 — status(관리자 승인)와 별개로 본인이 켜고 끄는 스위치.
    # FALSE면: B화면 카드 미노출 + 매물의뢰(K) 라우팅 대상에서 제외 (등록 데이터는 유지)
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS is_visible BOOLEAN DEFAULT TRUE")
    # 유료 우선노출용 점수 (현재 미사용, 기본 0 — loan_consultants.priority_score와 동일 패턴)
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS priority_score INTEGER DEFAULT 0")
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS office_phone TEXT")    # 사무실 유선전화(선택)
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS office_address TEXT")  # 사무소 소재지(선택)

    # 중개사별 담당(취육) 건물 + 매물 수 (B화면/중개사 개별페이지에서 사용 예정)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS agent_buildings (
        id SERIAL PRIMARY KEY,
        agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
        master_building_id INTEGER NOT NULL REFERENCES master_buildings(id) ON DELETE CASCADE,
        sale_count INTEGER DEFAULT 0,        -- 매매
        jeonse_count INTEGER DEFAULT 0,      -- 전세
        wolse_count INTEGER DEFAULT 0,       -- 월세
        shortterm_count INTEGER DEFAULT 0,   -- 단기
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT agent_buildings_agent_building_unique UNIQUE (agent_id, master_building_id)
    )
    """)
    cur.execute("ALTER TABLE agent_buildings ADD COLUMN IF NOT EXISTS presale_count INTEGER DEFAULT 0")
    cur.execute("ALTER TABLE agent_buildings ADD COLUMN IF NOT EXISTS has_priority_badge BOOLEAN DEFAULT FALSE")
    cur.execute("ALTER TABLE agent_buildings ADD COLUMN IF NOT EXISTS premium_granted_at TIMESTAMP")
    cur.execute("ALTER TABLE agent_buildings ADD COLUMN IF NOT EXISTS premium_expires_at TIMESTAMP")
    cur.execute("ALTER TABLE agent_buildings ADD COLUMN IF NOT EXISTS reminder_sent_at TIMESTAMP")
    cur.execute("ALTER TABLE agent_buildings ADD COLUMN IF NOT EXISTS is_paid BOOLEAN DEFAULT FALSE")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS agent_service_regions (
            id SERIAL PRIMARY KEY,
            agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
            sgg_text TEXT NOT NULL,
            umd_nm TEXT,
            granted_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP NOT NULL,
            CONSTRAINT agent_service_regions_unique
                UNIQUE (agent_id, sgg_text)
        )
    """)
    cur.execute("ALTER TABLE agent_service_regions ADD COLUMN IF NOT EXISTS umd_nm TEXT")
    cur.execute("ALTER TABLE agent_service_regions ADD COLUMN IF NOT EXISTS reminder_sent_at TIMESTAMP")
    cur.execute("ALTER TABLE agent_service_regions ADD COLUMN IF NOT EXISTS is_paid BOOLEAN DEFAULT FALSE")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS agent_region_buildings (
            id SERIAL PRIMARY KEY,
            agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
            master_building_id INTEGER NOT NULL REFERENCES master_buildings(id) ON DELETE CASCADE,
            added_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT agent_region_buildings_unique UNIQUE (agent_id, master_building_id)
        )
    """)

    # 기존 동 단위 행은 같은 중개사·시군구별 한 행으로 병합한 뒤 시군구 행으로 전환한다.
    # 중개사 기준 담당단지 연결은 삭제하지 않는다.
    cur.execute(
        "ALTER TABLE agent_service_regions "
        "DROP CONSTRAINT IF EXISTS agent_service_regions_agent_sgg_umd_unique"
    )
    cur.execute(
        "ALTER TABLE agent_service_regions "
        "DROP CONSTRAINT IF EXISTS agent_service_regions_unique"
    )
    merged_region_count, normalized_region_count = _migrate_agent_regions_to_sgg(cur)
    cur.execute("""
        ALTER TABLE agent_service_regions
        ADD CONSTRAINT agent_service_regions_unique UNIQUE (agent_id, sgg_text)
    """)
    cur.execute("DROP INDEX IF EXISTS idx_agent_service_regions_dong_expiry")
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_service_regions_sgg_expiry
        ON agent_service_regions(sgg_text, expires_at)
    """)
    if merged_region_count or normalized_region_count:
        print(
            "시군구 단위 지역뱃지 마이그레이션: "
            f"중복 지역 {merged_region_count}건 병합, "
            f"동 값 {normalized_region_count}건 초기화"
        )

    cur.execute("""
        CREATE TABLE IF NOT EXISTS premium_waitlist (
            id SERIAL PRIMARY KEY,
            agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
            master_building_id INTEGER NOT NULL REFERENCES master_buildings(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT NOW(),
            notified_at TIMESTAMP,
            CONSTRAINT premium_waitlist_unique UNIQUE (agent_id, master_building_id)
        )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS operators (
        id SERIAL PRIMARY KEY,
        company_name TEXT NOT NULL,         -- 업체명
        owner_name TEXT NOT NULL,           -- 대표자명
        category TEXT NOT NULL,             -- 위탁운영 | 청소 | 세탁 | 용품 | 대출상담사 | 인테리어
        biz_reg_number TEXT,                -- 사업자등록번호
        phone TEXT,
        email TEXT NOT NULL,
        website_url TEXT,
        status TEXT DEFAULT 'pending',      -- pending | approved | rejected | suspended
        created_at TIMESTAMP DEFAULT NOW(),
        approved_at TIMESTAMP,
        approved_by INTEGER REFERENCES admin_users(id)   -- 승인한 관리자 (admin_users.id 참조 FK)
    )
    """)
    # 기존에 이미 만들어진 DB에도 안전하게 컬럼 추가 (데이터 보존)
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS biz_reg_number TEXT")
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS phone TEXT")
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS website_url TEXT")
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending'")
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()")
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP")
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS approved_by INTEGER REFERENCES admin_users(id)")
    # 운영업체 로그인/공개페이지용 (agents와 동일 패턴, UNIQUE는 helper에서 안전하게 부여)
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS password_hash TEXT")
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS photo_url TEXT")
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS intro_text TEXT")
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS subdomain_slug TEXT")
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS admin_tag TEXT")  # 관리자 태그(일괄 관리용)
    # 파트너 소개 섹션용 로고 (Object Storage 참조 키 — applications/operator/{uuid}/logo.{ext})
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS logo_url TEXT")
    # 노출 여부 — agents.is_visible과 동일 개념 (본인 토글, FALSE면 B화면 카드 미노출)
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS is_visible BOOLEAN DEFAULT TRUE")
    # 유료 우선노출용 점수 (현재 미사용, 기본 0 — loan_consultants.priority_score와 동일 패턴)
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS priority_score INTEGER DEFAULT 0")
    # 업종명 정리: '위탁운영' → '위탁' (idempotent — 이미 '위탁'이면 아무 일도 안 일어남)
    cur.execute("UPDATE operators SET category='위탁' WHERE category='위탁운영'")

    # 운영업체별 담당 건물 (agent_buildings와 동일 패턴)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS operator_buildings (
        id SERIAL PRIMARY KEY,
        operator_id INTEGER NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
        master_building_id INTEGER NOT NULL REFERENCES master_buildings(id) ON DELETE CASCADE,
        note TEXT,                           -- 선택 (예: 담당 구역)
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT operator_buildings_operator_building_unique UNIQUE (operator_id, master_building_id)
    )
    """)
    cur.execute("ALTER TABLE operator_buildings ADD COLUMN IF NOT EXISTS has_priority_badge BOOLEAN DEFAULT FALSE")
    cur.execute("ALTER TABLE operator_buildings ADD COLUMN IF NOT EXISTS premium_granted_at TIMESTAMP")
    cur.execute("ALTER TABLE operator_buildings ADD COLUMN IF NOT EXISTS premium_expires_at TIMESTAMP")
    cur.execute("ALTER TABLE operator_buildings ADD COLUMN IF NOT EXISTS is_paid BOOLEAN DEFAULT FALSE")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS operator_service_areas (
            id SERIAL PRIMARY KEY,
            operator_id INTEGER NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
            region_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT operator_service_areas_unique UNIQUE (operator_id, region_name)
        )
    """)

    # 운영업체 지역Master 테이블 (중개사 agent_service_regions / agent_region_buildings와 동일 패턴)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS operator_service_regions (
            id SERIAL PRIMARY KEY,
            operator_id INTEGER NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
            sgg_text TEXT NOT NULL,
            granted_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP NOT NULL,
            is_paid BOOLEAN DEFAULT FALSE,
            CONSTRAINT operator_service_regions_unique UNIQUE (operator_id, sgg_text)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS operator_region_buildings (
            id SERIAL PRIMARY KEY,
            operator_id INTEGER NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
            master_building_id INTEGER NOT NULL REFERENCES master_buildings(id) ON DELETE CASCADE,
            added_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT operator_region_buildings_unique UNIQUE (operator_id, master_building_id)
        )
    """)

    # 대출상담사 — 위탁운영/청소 등 운영지원업체(operators)와 완전히 분리된 별도 엔티티.
    # agents 테이블과 동일 패턴 (승인 시 slug/임시비밀번호 발급 가능 구조).
    cur.execute("""
    CREATE TABLE IF NOT EXISTS loan_consultants (
        id SERIAL PRIMARY KEY,
        office_name TEXT NOT NULL,          -- 소속 회사/법인명
        owner_name TEXT NOT NULL,           -- 상담사 성명
        license_number TEXT NOT NULL,       -- 대출모집인 등록번호 (UNIQUE는 helper에서 안전하게 부여)
        biz_reg_number TEXT,                -- 사업자등록번호(선택)
        phone TEXT,
        email TEXT NOT NULL,
        status TEXT DEFAULT 'pending',      -- pending | approved | rejected | suspended
        subdomain_slug TEXT,                -- 승인 시 발급 (UNIQUE는 helper에서 부여)
        intro_text TEXT,
        password_hash TEXT,
        photo_url TEXT,
        admin_tag TEXT,
        created_at TIMESTAMP DEFAULT NOW(),
        approved_at TIMESTAMP,
        approved_by INTEGER REFERENCES admin_users(id)
    )
    """)
    cur.execute("ALTER TABLE loan_consultants ADD COLUMN IF NOT EXISTS logo_url TEXT")  # 파트너 로고(이번엔 스키마만 준비)
    # 노출 여부 — agents.is_visible과 동일 개념 (본인 토글)
    cur.execute("ALTER TABLE loan_consultants ADD COLUMN IF NOT EXISTS is_visible BOOLEAN DEFAULT TRUE")
    # 상담 가능 상품(콤마구분 텍스트) / 카카오톡 상담 링크 / 유료 우선노출용 점수(현재 미사용, 기본 0)
    cur.execute("ALTER TABLE loan_consultants ADD COLUMN IF NOT EXISTS consultant_products TEXT")
    cur.execute("ALTER TABLE loan_consultants ADD COLUMN IF NOT EXISTS kakao_chat_url TEXT")
    cur.execute("ALTER TABLE loan_consultants ADD COLUMN IF NOT EXISTS priority_score INTEGER DEFAULT 0")
    # 취급지역 (전국/수도권/시도 — 허용값은 app.py LOAN_SERVICE_REGIONS). NULL이면 화면에서 '전국'으로 표시
    cur.execute("ALTER TABLE loan_consultants ADD COLUMN IF NOT EXISTS service_region TEXT")

    # 대출상담사별 담당 건물 (agent_buildings/operator_buildings와 동일 패턴)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS loan_consultant_buildings (
        id SERIAL PRIMARY KEY,
        loan_consultant_id INTEGER NOT NULL REFERENCES loan_consultants(id) ON DELETE CASCADE,
        master_building_id INTEGER NOT NULL REFERENCES master_buildings(id) ON DELETE CASCADE,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT loan_consultant_buildings_unique UNIQUE (loan_consultant_id, master_building_id)
    )
    """)
    cur.execute("ALTER TABLE loan_consultant_buildings ADD COLUMN IF NOT EXISTS has_priority_badge BOOLEAN DEFAULT FALSE")
    cur.execute("ALTER TABLE loan_consultant_buildings ADD COLUMN IF NOT EXISTS premium_granted_at TIMESTAMP")
    cur.execute("ALTER TABLE loan_consultant_buildings ADD COLUMN IF NOT EXISTS premium_expires_at TIMESTAMP")
    cur.execute("ALTER TABLE loan_consultant_buildings ADD COLUMN IF NOT EXISTS is_paid BOOLEAN DEFAULT FALSE")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS loan_consultant_service_areas (
        id SERIAL PRIMARY KEY,
        loan_consultant_id INTEGER NOT NULL REFERENCES loan_consultants(id) ON DELETE CASCADE,
        region_name TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT loan_consultant_service_areas_unique UNIQUE (loan_consultant_id, region_name)
    )
    """)
    # 기존 단일 취급지역(service_region) 값을 다중선택 테이블로 1회 이관(idempotent)
    cur.execute("""
        INSERT INTO loan_consultant_service_areas (loan_consultant_id, region_name)
        SELECT id, COALESCE(NULLIF(service_region, ''), '전국') FROM loan_consultants
        ON CONFLICT (loan_consultant_id, region_name) DO NOTHING
    """)
    # 관리자 메모(비고) — 회원관리 목록에서 인라인 수정 + 비활성화 사유 자동 누적
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS admin_memo TEXT")
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS admin_memo TEXT")
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS admin_memo TEXT")
    cur.execute("ALTER TABLE loan_consultants ADD COLUMN IF NOT EXISTS admin_memo TEXT")

    # 회원 상세페이지 신규 필드 (2026-08-11) ─ 전 회원 유형 공통
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS business_reg_number TEXT")        # 사업자등록번호(일반회원 전용 — 파트너는 기존 biz_reg_number 사용)
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS tax_invoice_email TEXT")           # 세금계산서 발행용 이메일
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS rejection_reason TEXT")            # 가입 반려 사유(재신청 시 덮어씀)
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS tax_invoice_email TEXT")
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS rejection_reason TEXT")
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS manager_name TEXT")               # 담당자명(대표자와 다를 수 있음)
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS desired_building TEXT")           # 희망건물(가입 시 자유 텍스트)
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS tax_invoice_email TEXT")
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS rejection_reason TEXT")
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS manager_name TEXT")
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS desired_building TEXT")
    cur.execute("ALTER TABLE loan_consultants ADD COLUMN IF NOT EXISTS tax_invoice_email TEXT")
    cur.execute("ALTER TABLE loan_consultants ADD COLUMN IF NOT EXISTS rejection_reason TEXT")
    cur.execute("ALTER TABLE loan_consultants ADD COLUMN IF NOT EXISTS manager_name TEXT")
    cur.execute("ALTER TABLE loan_consultants ADD COLUMN IF NOT EXISTS desired_building TEXT")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS applications (
        id SERIAL PRIMARY KEY,
        applicant_type TEXT NOT NULL,            -- 'agent' | 'operator'
        office_or_company_name TEXT NOT NULL,    -- 중개사무소명 또는 업체명 공용
        owner_name TEXT NOT NULL,
        reg_number TEXT,                         -- 중개사무소 등록번호 (agent만 해당)
        biz_reg_number TEXT,                     -- 사업자등록번호 (공용)
        category TEXT,                           -- 업종 (operator만: 위탁운영/청소/세탁/용품/대출상담사/인테리어)
        phone TEXT NOT NULL,
        email TEXT NOT NULL,
        website_url TEXT,
        preferred_region TEXT,                   -- 희망 지역(선택)
        preferred_building TEXT,                 -- 희망 건물(선택)
        intro_text TEXT,                         -- 자기소개(선택, agent 주로)
        doc_license_url TEXT,                    -- 공인중개사 자격증 사본 (agent)
        doc_office_reg_url TEXT,                 -- 중개사무소 등록증 사본 (agent)
        doc_biz_reg_url TEXT,                    -- 사업자등록증 사본 (공용)
        doc_business_card_url TEXT,              -- 명함 (operator)
        doc_biz_license_url TEXT,                -- 영업허가증 (operator, 업종별 조건부)
        status TEXT DEFAULT 'submitted',         -- submitted | reviewing | approved | rejected
        reject_reason TEXT,
        linked_agent_id INTEGER REFERENCES agents(id),        -- 승인 시 반영된 agents.id (FK)
        linked_operator_id INTEGER REFERENCES operators(id),  -- 승인 시 반영된 operators.id (FK)
        reviewed_by INTEGER REFERENCES admin_users(id),       -- 검토한 관리자 (admin_users.id FK)
        submitted_at TIMESTAMP DEFAULT NOW(),
        reviewed_at TIMESTAMP
    )
    """)
    # 기존에 이미 만들어진 DB에도 안전하게 컬럼 추가 (데이터 보존)
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS reg_number TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS biz_reg_number TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS category TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS website_url TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS preferred_region TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS preferred_building TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS intro_text TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS intro_title TEXT")  # 소개글 제목(16자, agent)
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS doc_license_url TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS doc_office_reg_url TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS doc_biz_reg_url TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS doc_business_card_url TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS doc_biz_license_url TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS doc_logo_url TEXT")  # 로고 이미지(선택, 운영지원업체)
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS office_address TEXT")
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS office_address TEXT")
    cur.execute("ALTER TABLE loan_consultants ADD COLUMN IF NOT EXISTS office_address TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'submitted'")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS reject_reason TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS linked_agent_id INTEGER REFERENCES agents(id)")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS linked_operator_id INTEGER REFERENCES operators(id)")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS reviewed_by INTEGER REFERENCES admin_users(id)")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMP DEFAULT NOW()")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP")
    # 법적 동의 이력 (신청 시 필수 동의 시각 — 기존 행은 NULL 허용)
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS terms_agreed_at TIMESTAMP")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS privacy_agreed_at TIMESTAMP")
    # 대출상담사(applicant_type='loan_consultant') 승인 시 연결되는 loan_consultants.id
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS linked_loan_consultant_id INTEGER REFERENCES loan_consultants(id)")
    # 건물 상세(B화면)에서 신청 시 담아오는 희망건물 id — 승인 시 agent_buildings 자동 배정용
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS preferred_building_id INTEGER REFERENCES master_buildings(id)")
    # 중개사 여권용 사진 (선택 · Object Storage 참조 키 — applications/agent/{uuid}/photo.{ext})
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS doc_photo_url TEXT")
    # 단지부동산(상가정보 API 배치 동기화) — 업종대분류 "부동산" 업소 상호를 콤마 join 하여 저장.
    # NULL = 아직 조회 안 됨, "" = 조회했으나 부동산 업소 없음
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS realty_store_name TEXT")
    # 마지막 상가정보 API 조회 시각 — NULL이면 미조회, 오래된 순으로 재조회 우선
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS realty_checked_at TIMESTAMP")
    # 신청서 수정/취소용 이메일 링크 토큰 — 신청 접수 시 1회 발급, URL-safe 랜덤 문자열.
    # status가 'submitted'(검토 시작 전)일 때만 이 토큰으로 본인 신청 내용을 조회·수정·취소할 수 있다.
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS edit_token TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS password_hash TEXT")
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_applications_edit_token
        ON applications(edit_token) WHERE edit_token IS NOT NULL
    """)

    # 매출/광고 장부 — 결제 연동 전 관리자 수동 기록 (계좌이체 확인 후 입력).
    # partner_type+partner_id 로 agents/operators/loan_consultants 를 가리킨다 (다형 참조라 FK 없음).
    cur.execute("""
    CREATE TABLE IF NOT EXISTS revenue_records (
        id SERIAL PRIMARY KEY,
        partner_type TEXT NOT NULL CHECK (partner_type IN ('agent', 'operator', 'loan_consultant')),
        partner_id INTEGER NOT NULL,
        product_type TEXT NOT NULL CHECK (product_type IN ('building_slot', 'priority_exposure')),
        start_date DATE NOT NULL,
        end_date DATE,                       -- NULL 허용(무기한/미정)
        amount INTEGER NOT NULL DEFAULT 0,   -- 원 단위
        payment_status TEXT NOT NULL DEFAULT '대기' CHECK (payment_status IN ('대기', '완료', '만료')),
        memo TEXT,
        created_at TIMESTAMP DEFAULT NOW(),
        created_by INTEGER REFERENCES admin_users(id)
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_revenue_partner ON revenue_records (partner_type, partner_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_revenue_start ON revenue_records (start_date)")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS slots (
        id SERIAL PRIMARY KEY,
        master_building_id INTEGER NOT NULL REFERENCES master_buildings(id),  -- 건물 (FK)
        agent_id INTEGER NOT NULL REFERENCES agents(id),                      -- 중개사 (FK)
        status TEXT DEFAULT 'active',        -- active | waiting | expired
        queue_position INTEGER,              -- status='waiting'일 때 대기 순번, active면 NULL
        monthly_fee INTEGER,                 -- 월 회비(원 단위)
        started_at TIMESTAMP,
        expires_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """)
    # 기존에 이미 만들어진 DB에도 안전하게 컬럼 추가 (데이터 보존)
    cur.execute("ALTER TABLE slots ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active'")
    cur.execute("ALTER TABLE slots ADD COLUMN IF NOT EXISTS queue_position INTEGER")
    cur.execute("ALTER TABLE slots ADD COLUMN IF NOT EXISTS monthly_fee INTEGER")
    cur.execute("ALTER TABLE slots ADD COLUMN IF NOT EXISTS started_at TIMESTAMP")
    cur.execute("ALTER TABLE slots ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP")
    cur.execute("ALTER TABLE slots ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS listings (
        id SERIAL PRIMARY KEY,
        master_building_id INTEGER NOT NULL REFERENCES master_buildings(id),  -- 건물 (FK)
        agent_id INTEGER REFERENCES agents(id),   -- 중개사 (FK, NULL 허용 — 소유주 직접 등록 대비)
        deal_type TEXT NOT NULL,                  -- 매매 | 전세 | 월세
        price INTEGER,                            -- 매매가 또는 보증금(만원 단위)
        monthly_rent INTEGER,                     -- 월세인 경우 월 임대료(만원 단위), 그 외 NULL
        floor TEXT,
        area REAL,                                -- 전용면적(㎡)
        status TEXT DEFAULT 'active',             -- active | completed | hidden
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )
    """)
    # 기존에 이미 만들어진 DB에도 안전하게 컬럼 추가 (데이터 보존)
    cur.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS agent_id INTEGER REFERENCES agents(id)")
    cur.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS price INTEGER")
    cur.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS monthly_rent INTEGER")
    cur.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS floor TEXT")
    cur.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS area REAL")
    cur.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active'")
    cur.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()")
    cur.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW()")

    # 관리자 수정 감사 로그 — 실거래(공공데이터 원본)처럼 함부로 고치면 안 되는 값을
    # 정정할 때 old/new 값과 사유(reason)를 필드 단위로 남긴다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS admin_edit_log (
        id SERIAL PRIMARY KEY,
        table_name TEXT NOT NULL,        -- 수정 대상 테이블명 (예: transactions)
        record_id INTEGER NOT NULL,      -- 수정된 행의 id
        field TEXT NOT NULL,             -- 수정된 컬럼명
        old_value TEXT,                  -- 수정 전 값 (문자열로 보관)
        new_value TEXT,                  -- 수정 후 값 (문자열로 보관)
        reason TEXT NOT NULL,            -- 관리자가 입력한 수정 사유 (필수)
        admin BOOLEAN DEFAULT TRUE,      -- 관리자 권한으로 수정했는지 여부
        edited_at TIMESTAMP DEFAULT NOW()
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS mileage_missions (
        id SERIAL PRIMARY KEY,
        code TEXT NOT NULL,              -- 예: photo_exterior, admin_consent (UNIQUE는 helper에서 안전하게 부여)
        title TEXT NOT NULL,             -- 예: 건물 외관 사진
        points INTEGER NOT NULL,
        tier TEXT DEFAULT 'basic',       -- basic | top | top2 (★, ★★ 구분)
        active BOOLEAN DEFAULT TRUE
    )
    """)
    # 기존에 이미 만들어진 DB에도 안전하게 컬럼 추가 (데이터 보존)
    cur.execute("ALTER TABLE mileage_missions ADD COLUMN IF NOT EXISTS tier TEXT DEFAULT 'basic'")
    cur.execute("ALTER TABLE mileage_missions ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT TRUE")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS mileage_submissions (
        id SERIAL PRIMARY KEY,
        agent_id INTEGER NOT NULL REFERENCES agents(id),                 -- 중개사 (FK)
        mission_id INTEGER NOT NULL REFERENCES mileage_missions(id),     -- 미션 (FK)
        master_building_id INTEGER REFERENCES master_buildings(id),      -- 건물 (FK, NULL 허용)
        photo_urls TEXT,                 -- JSON 문자열로 여러 장 저장(우선 TEXT, 나중에 JSONB 검토)
        status TEXT DEFAULT 'pending',   -- pending | verified | rejected
        points_awarded INTEGER,
        submitted_at TIMESTAMP DEFAULT NOW(),
        reviewed_at TIMESTAMP,
        reviewed_by INTEGER REFERENCES admin_users(id)                   -- 검토한 관리자 (FK)
    )
    """)
    # 기존에 이미 만들어진 DB에도 안전하게 컬럼 추가 (데이터 보존)
    cur.execute("ALTER TABLE mileage_submissions ADD COLUMN IF NOT EXISTS master_building_id INTEGER REFERENCES master_buildings(id)")
    cur.execute("ALTER TABLE mileage_submissions ADD COLUMN IF NOT EXISTS photo_urls TEXT")
    cur.execute("ALTER TABLE mileage_submissions ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending'")
    cur.execute("ALTER TABLE mileage_submissions ADD COLUMN IF NOT EXISTS points_awarded INTEGER")
    cur.execute("ALTER TABLE mileage_submissions ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMP DEFAULT NOW()")
    cur.execute("ALTER TABLE mileage_submissions ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP")
    cur.execute("ALTER TABLE mileage_submissions ADD COLUMN IF NOT EXISTS reviewed_by INTEGER REFERENCES admin_users(id)")

    # 방문 기록(페이지뷰) — 통계 대시보드용. 개인정보 최소수집: 원본 IP 대신 salt 해시만 저장.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS page_views (
        id SERIAL PRIMARY KEY,
        path TEXT NOT NULL,                -- 조회한 사용자 페이지 경로 (/ , /building/<id> 등)
        listing_request_id INTEGER,        -- /building/<id>?listing=<id>로 연 매물 (없으면 NULL)
        ip_hash TEXT,                      -- sha256(방문자IP + 고정 salt) — 원본 IP는 저장 안 함
        user_agent TEXT,                   -- 브라우저 UA 문자열 (참고용)
        viewed_at TIMESTAMP DEFAULT NOW()
    )
    """)
    cur.execute("ALTER TABLE page_views ADD COLUMN IF NOT EXISTS listing_request_id INTEGER")

    # 전국 도시철도역 좌표 — 공공데이터 1회성 import로 채우며, 없는 지역은 null로 처리한다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS subway_stations (
        id SERIAL PRIMARY KEY,
        station_name TEXT NOT NULL,
        line_name TEXT,
        lat DOUBLE PRECISION NOT NULL,
        lng DOUBLE PRECISION NOT NULL
    )
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS subway_stations_dedupe_uidx
        ON subway_stations (station_name, COALESCE(line_name, ''), lat, lng)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS subway_stations_lat_lng_idx
        ON subway_stations (lat, lng)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS master_buildings_lat_lng_idx
        ON master_buildings (lat, lng)
        WHERE lat IS NOT NULL AND lng IS NOT NULL
    """)

    # 일반 회원 — 이메일/비밀번호 또는 카카오 소셜 로그인. (관리자 admin_users와는 별개 테이블)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        email TEXT,                        -- 로그인 아이디. UNIQUE는 _ensure_users_unique_constraints()에서 부여
        password_hash TEXT,                -- werkzeug 해시. 카카오 전용 가입자는 NULL(비밀번호 없음)
        name TEXT,                         -- 표시용 이름/닉네임
        provider TEXT DEFAULT 'email',     -- 'email' | 'kakao'
        kakao_id TEXT,                     -- 카카오 회원번호. UNIQUE는 helper에서 부여(NULL 허용)
        user_type TEXT NOT NULL DEFAULT 'general',  -- general | owner | operator
        created_at TIMESTAMP DEFAULT NOW(),
        last_login_at TIMESTAMP,           -- 마지막 로그인 시각 (로그인 시 갱신)
        status TEXT DEFAULT 'active'       -- 'active' | 'withdrawn'(회원탈퇴 소프트삭제)
    )
    """)
    # 기존에 이미 만들어진 DB에도 안전하게 컬럼 추가 (데이터 보존)
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS name TEXT")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS provider TEXT DEFAULT 'email'")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS kakao_id TEXT")
    # 주간 기능 소개 등 회원 대상 콘텐츠의 유형 구분. 기존 회원은 일반회원으로
    # 보정해 과거 데이터의 NULL/예상 밖 값으로 발송 작업이 중단되지 않게 한다.
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS user_type TEXT DEFAULT 'general'")
    cur.execute("""
        UPDATE users SET user_type = 'general'
        WHERE user_type IS NULL OR user_type NOT IN ('general', 'owner', 'operator')
    """)
    cur.execute("ALTER TABLE users ALTER COLUMN user_type SET DEFAULT 'general'")
    cur.execute("ALTER TABLE users ALTER COLUMN user_type SET NOT NULL")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active'")
    # 법적 동의 이력 (이메일 회원가입 시 기록. 카카오 간편가입은 추후 별도 적용 예정이라 NULL 허용)
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_agreed_at TIMESTAMP")      # [필수] 이용약관 동의 시각
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS privacy_agreed_at TIMESTAMP")    # [필수] 개인정보 수집·이용 동의 시각
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS marketing_agreed_at TIMESTAMP")  # [선택] 마케팅 수신 동의 시각(미동의 NULL)
    # 일괄 관리(관리자) — 포인트 잔액 + 관리자 태그
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS points INTEGER DEFAULT 0")
    # 실거래 이메일 알림 수신 여부 (기본 켜짐 — 마이페이지에서 끌 수 있음)
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email_alert_enabled BOOLEAN DEFAULT TRUE")
    # 주간 소식 이메일 수신 동의 (기본 켜짐 — 마이페이지에서 끌 수 있음)
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS weekly_email_enabled BOOLEAN DEFAULT TRUE")
    cur.execute("ALTER TABLE users ALTER COLUMN weekly_email_enabled SET DEFAULT TRUE")
    # NULL은 과거 환경에서 동의 상태가 기록되지 않은 행일 수 있으므로 TRUE로 정규화한다.
    cur.execute("UPDATE users SET weekly_email_enabled = TRUE WHERE weekly_email_enabled IS NULL")

    # 이메일 회원 비밀번호 재설정 — URL 원문 대신 SHA-256 다이제스트만 DB에
    # 저장한다. user 삭제 시 토큰도 함께 정리한다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS password_reset_tokens (
        id SERIAL PRIMARY KEY,
        -- 계정 유형에 따라 users/agents/operators/loan_consultants의 id를 담는다.
        user_id INTEGER NOT NULL,
        account_type TEXT NOT NULL DEFAULT 'user',
        token TEXT NOT NULL UNIQUE,          -- URL 토큰의 SHA-256 다이제스트
        expires_at TIMESTAMP NOT NULL,
        used_at TIMESTAMP,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """)
    # 기존 테이블은 users만 참조하는 FK로 만들어져 있었으므로, 다른 회원
    # 테이블의 id도 담을 수 있는 계정 공통 식별자로 전환한다.
    cur.execute(
        "ALTER TABLE password_reset_tokens DROP CONSTRAINT IF EXISTS password_reset_tokens_user_id_fkey"
    )
    cur.execute(
        "ALTER TABLE password_reset_tokens ADD COLUMN IF NOT EXISTS account_type TEXT DEFAULT 'user'"
    )
    cur.execute(
        "UPDATE password_reset_tokens SET account_type = 'user' WHERE account_type IS NULL"
    )
    cur.execute(
        "ALTER TABLE password_reset_tokens ALTER COLUMN account_type SET DEFAULT 'user'"
    )
    cur.execute(
        "ALTER TABLE password_reset_tokens ALTER COLUMN account_type SET NOT NULL"
    )
    cur.execute("""
        CREATE INDEX IF NOT EXISTS password_reset_tokens_token_idx
        ON password_reset_tokens (token)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS password_reset_tokens_user_idx
        ON password_reset_tokens (user_id, created_at DESC)
    """)
    # 자동 opt-in이 명시적 수신거부를 되살리지 않도록 마지막 명시적 변경 시각을 보관한다.
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_weekly_email_at TIMESTAMP")
    # 과거에는 변경 시각이 없었으므로 FALSE가 기본 미동의인지 명시적 off인지 구분할 수 없다.
    # 개인정보 보호상 FALSE는 명시적 off로 간주해 보존한다. 신규 회원은 위 기본값(TRUE)을 받는다.
    cur.execute("""
        UPDATE users
           SET updated_weekly_email_at = NOW()
         WHERE weekly_email_enabled = FALSE
           AND updated_weekly_email_at IS NULL
    """)
    # 원클릭 수신거부용 UUID 토큰 (로그인 없이 이메일 링크 하나로 수신거부 처리)
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS unsubscribe_token UUID")
    cur.execute("UPDATE users SET unsubscribe_token = gen_random_uuid() WHERE unsubscribe_token IS NULL")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS admin_tag TEXT")
    # 매물 직거래 — 휴대폰 인증
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_verified BOOLEAN DEFAULT FALSE")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_code TEXT")            # 6자리 OTP
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_code_expires_at TIMESTAMP")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_code_target TEXT")     # 인증 중인 번호

    # 일반회원 로그인 감사 이력 — IP 원문은 저장하지 않고 앱에서 해시해 기록한다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS login_history (
        id           SERIAL PRIMARY KEY,
        user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        logged_in_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        ip_hash      TEXT,
        user_agent   TEXT
    )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_login_history_user
        ON login_history (user_id, logged_in_at DESC)
    """)
    # 테이블 도입 전에 로그인한 기존 회원도 마지막 로그인 1건은 표시한다.
    cur.execute("""
        INSERT INTO login_history (user_id, logged_in_at)
        SELECT u.id, u.last_login_at
          FROM users u
         WHERE u.last_login_at IS NOT NULL
           AND NOT EXISTS (
               SELECT 1 FROM login_history lh
                WHERE lh.user_id = u.id
           )
    """)

    # 사업주 매물 등록 자격 확인 — 사용자·건물별 대표 영업신고번호 인증 캐시
    cur.execute("""
    CREATE TABLE IF NOT EXISTS business_building_verifications (
        id                  SERIAL PRIMARY KEY,
        user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        master_building_id  INTEGER NOT NULL REFERENCES master_buildings(id) ON DELETE CASCADE,
        permit_number       TEXT NOT NULL,
        verified_at         TIMESTAMP NOT NULL DEFAULT NOW(),
        UNIQUE (user_id, master_building_id)
    )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_business_building_verifications_building
        ON business_building_verifications(master_building_id)
    """)

    # 이메일 광고 배너 (주간 이메일 Zone 5)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS email_ad_banners (
        id         SERIAL PRIMARY KEY,
        image_url  TEXT NOT NULL,
        link_url   TEXT NOT NULL,
        start_date DATE NOT NULL,
        end_date   DATE NOT NULL,
        is_active  BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """)

    # 포인트 변경 이력(감사로그) — 양수=지급, 음수=차감. 삭제하지 않고 계속 쌓는다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS point_transactions (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        amount INTEGER NOT NULL,                          -- 양수=지급, 음수=차감 (0 금지 — 앱에서 검증)
        reason TEXT NOT NULL,                             -- 지급/차감 사유 (필수)
        admin_id INTEGER REFERENCES admin_users(id),      -- 처리한 관리자
        created_at TIMESTAMP DEFAULT NOW()
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_point_tx_user ON point_transactions(user_id, created_at DESC)")

    # 관리자 메모 이력 — 전 회원 유형 공통 (member_type 로 구분, FK 없음)
    # 기본 append-only; super_admin은 수정(updated_at 갱신) 및 소프트 삭제(is_deleted=TRUE) 가능.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS member_notes (
        id SERIAL PRIMARY KEY,
        member_type TEXT NOT NULL,          -- 'general'|'agent'|'operator'|'loan_consultant'
        member_id INTEGER NOT NULL,
        memo_date DATE NOT NULL DEFAULT CURRENT_DATE,
        content TEXT NOT NULL,
        author_name VARCHAR(50) NOT NULL DEFAULT '관리자',
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP,
        is_deleted BOOLEAN NOT NULL DEFAULT FALSE
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_member_notes_member ON member_notes(member_type, member_id, created_at DESC)")

    # 첨부서류(다중 파일) — 회원 상세페이지 인라인 미리보기용 (object storage 키 저장)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS member_documents (
        id SERIAL PRIMARY KEY,
        member_type TEXT NOT NULL,          -- 'general'|'agent'|'operator'|'loan_consultant'
        member_id INTEGER NOT NULL,
        doc_type VARCHAR(30) NOT NULL,      -- 'business_license'|'business_card'|'permit'
        file_key TEXT NOT NULL,             -- object storage 키(서명 URL 발급용)
        file_type VARCHAR(10) NOT NULL,     -- 'pdf'|'jpg'|'png'
        uploaded_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_member_docs_member ON member_documents(member_type, member_id)")

    # 매물 의뢰(일반 회원 → 중개사 라우팅) — users 테이블 뒤에 생성해야 FK가 성립한다.
    # 라우팅 우선순위: exclusive(그 건물 전속 중개사) > region(같은 시군구 활동 중개사) > house(하우스 계정).
    cur.execute("""
    CREATE TABLE IF NOT EXISTS listing_requests (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),              -- 의뢰한 회원 (로그인 필수)
        master_building_id INTEGER NOT NULL REFERENCES master_buildings(id),
        deal_type TEXT NOT NULL,          -- 매매 | 전세 | 월세 | 단기임대
        desired_price TEXT,               -- 희망가 사람이 읽는 문자열 (예: "매매가 12,000만원") — 호환성 유지
        price_krw INTEGER,                -- 매매가/보증금 또는 사업주 임대 최저가 (만원 단위 숫자)
        price_krw_max INTEGER,            -- 사업주 월세·단기임대 가격범위의 최고가 (만원 단위 숫자)
        monthly_rent_krw INTEGER,         -- 월세 (만원 단위 숫자) — 월세 유형에서만 사용
        room_count INTEGER,               -- 사업주가 입력한 총 호실수
        contact_phone TEXT NOT NULL,      -- 중개사가 연락할 번호
        routed_agent_id INTEGER REFERENCES agents(id),  -- 배정된 대표 중개사 (없으면 NULL)
        routed_reason TEXT,               -- exclusive | region | house
        status TEXT DEFAULT 'submitted',  -- submitted(신규) | in_progress(처리중) | done(완료) — 중개사만 순방향 변경 가능
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP
    )
    """)
    # 기존 DB에도 안전하게 컬럼 추가 — 관리자 전용 메모(중개사에게는 노출 안 함)
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS admin_note TEXT")
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP")
    # 거래유형별 구조화 희망가(만원 단위 숫자) — desired_price(텍스트)와 병행 저장
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS price_krw INTEGER")
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS price_krw_max INTEGER")
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS monthly_rent_krw INTEGER")
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS room_count INTEGER")
    # 진행방식: 'direct'(직거래) | 'broker'(중개사 연결)
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS deal_mode TEXT DEFAULT 'broker'")
    # 직거래 공개 매물 연락처 (인증된 번호)
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS verified_phone TEXT")
    # 전용면적(㎡) — 선택 입력, 공개 표시용
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS area_sqm NUMERIC")
    # 상세주소(동/호) — 비공개, 추후 소유자 인증용
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS dong VARCHAR(20)")
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS ho VARCHAR(20)")
    # 등록자 유형: 'owner' | 'agent' | 'other'
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS registrant_type VARCHAR(20)")
    # 물건설명 (선택, 최대 500자 권장)
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS description TEXT")
    # 수익률 계산용 보증금 (만원 단위) — 매매 거래유형에서 yield_rate 계산 시 입력
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS deposit_krw INTEGER")
    # 계산된 수익률 (참고용, %) — (월세×12)/(매매가−보증금)×100
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS yield_rate NUMERIC")
    # 수익률 산출에 사용한 월 임대료(만원) — 매매/전세 매물도 별도로 보관
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS yield_rent_krw INTEGER")
    # 거래대상 — 기존 행은 모두 개별호실(unit)로 해석한다.
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS transaction_target TEXT DEFAULT 'unit'")
    # 건물전체 거래·운영 정보. 금액은 모두 만원 단위 정수다.
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS succession_loan_krw INTEGER")
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS key_money_krw INTEGER")
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS monthly_revenue_krw INTEGER")
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS annual_revenue_krw INTEGER")
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS operation_status TEXT")
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS closed_at DATE")
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS remodeling_info TEXT")
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS is_urgent BOOLEAN DEFAULT FALSE")
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS disclosure_scope TEXT DEFAULT 'limited'")
    # 마스터 원본이 비어 있는 건물정보의 매물별 직접입력 보정값.
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS building_info_overrides JSONB DEFAULT '{}'::jsonb")
    # 매물 등록 시점의 인증된 숙박업 신고번호와 선택 운영지표.
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS matched_permit_number TEXT")
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS short_stay_ratio NUMERIC")
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS ota_revenue_ratio NUMERIC")
    # 지도 마커의 공개 직거래 활성 매물 건수 집계 — 건물별 LATERAL COUNT의 전체 스캔 방지
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_listing_requests_active_direct_building
        ON listing_requests(master_building_id)
        WHERE deal_mode = 'direct'
          AND COALESCE(status, '') NOT IN ('withdrawn', '철회됨')
    """)

    # 대외 표시번호(내부 id와 분리) — deal_mode별 독립 채번 (직거래001001 / 중개001001)
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS display_seq INTEGER")
    # (deal_mode, display_seq) 조합 유니크 — 부분 인덱스는 ON CONFLICT 추론 문제로
    # 여기서는 순수 조회/제약용이므로 WHERE display_seq IS NOT NULL 부분 인덱스로 충분.
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_lr_dealmode_seq
        ON listing_requests(deal_mode, display_seq)
        WHERE display_seq IS NOT NULL
    """)
    # deal_mode별 독립 시퀀스 — 1001부터 시작(표시 형식은 6자리 zero-pad → 001001)
    cur.execute("CREATE SEQUENCE IF NOT EXISTS listing_seq_direct START WITH 1001")
    cur.execute("CREATE SEQUENCE IF NOT EXISTS listing_seq_broker START WITH 1001")
    # 기존 데이터 1회성 소급 채번 — display_seq가 비어있는 행만, 등록 순서(id ASC)대로.
    # 이미 채번된 행이 있으면 그 최대값 다음부터 이어붙인다(재실행해도 안전).
    for _mode, _seq in (("direct", "listing_seq_direct"), ("broker", "listing_seq_broker")):
        cur.execute("""
            WITH ranked AS (
                SELECT id,
                       COALESCE((SELECT MAX(display_seq) FROM listing_requests WHERE deal_mode = %s), 1000)
                       + ROW_NUMBER() OVER (ORDER BY id ASC) AS seq
                FROM listing_requests
                WHERE deal_mode = %s AND display_seq IS NULL
            )
            UPDATE listing_requests lr SET display_seq = ranked.seq
            FROM ranked WHERE lr.id = ranked.id
        """, (_mode, _mode))
        # 시퀀스를 현재 최대 번호에 맞춤 — 없으면 1000으로 세팅해 다음 nextval()이 1001.
        cur.execute(f"""
            SELECT setval('{_seq}',
                          COALESCE((SELECT MAX(display_seq) FROM listing_requests WHERE deal_mode = %s), 1000))
        """, (_mode,))

    # 건물전체 매물 실사 체크리스트 — 로그인 회원의 사용자·매물별 항목 진행 상태.
    # 비로그인 상태는 프런트 localStorage로 처리해 사용자 계정 정보와 섞지 않는다.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS listing_checklist_progress (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            listing_request_id INTEGER NOT NULL REFERENCES listing_requests(id) ON DELETE CASCADE,
            item_key TEXT NOT NULL,
            checked_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, listing_request_id, item_key)
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS ix_listing_checklist_progress_listing_user
        ON listing_checklist_progress(listing_request_id, user_id)
    """)

    # 방 재고 — 매물의뢰 등록자가 관리하는 객실별 월세·입실/공실·계약만기일·판매 채널.
    # 만기임박은 저장 상태가 아니라 contract_end_date와 오늘 날짜로 화면에서 계산한다.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS business_room_inventory (
            id SERIAL PRIMARY KEY,
            listing_request_id INTEGER NOT NULL
                REFERENCES listing_requests(id) ON DELETE CASCADE,
            room_label TEXT NOT NULL,
            deposit_krw INTEGER,
            monthly_rent_krw INTEGER,
            status TEXT NOT NULL DEFAULT '공실',
            contract_end_date DATE,
            floor INTEGER,
            channel TEXT NOT NULL DEFAULT '장박가능',
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP,
            UNIQUE (listing_request_id, room_label)
        )
    """)
    cur.execute(
        "ALTER TABLE business_room_inventory "
        "ADD COLUMN IF NOT EXISTS contract_end_date DATE"
    )
    cur.execute(
        "ALTER TABLE business_room_inventory "
        "ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP"
    )
    cur.execute(
        "ALTER TABLE business_room_inventory "
        "ADD COLUMN IF NOT EXISTS floor INTEGER"
    )
    cur.execute(
        "ALTER TABLE business_room_inventory "
        "ADD COLUMN IF NOT EXISTS channel TEXT DEFAULT '장박가능'"
    )
    cur.execute(
        "ALTER TABLE business_room_inventory "
        "ADD COLUMN IF NOT EXISTS monthly_rent_krw INTEGER"
    )
    cur.execute(
        "ALTER TABLE business_room_inventory "
        "ADD COLUMN IF NOT EXISTS deposit_krw INTEGER"
    )
    # 이전/수동 데이터가 있더라도 만기임박은 입실로 보존하고, 알 수 없는 값은 공실로 정리한다.
    cur.execute("""
        UPDATE business_room_inventory
           SET status = '입실'
         WHERE status = '만기임박'
    """)
    cur.execute("""
        UPDATE business_room_inventory
           SET status = '공실'
         WHERE status IS NULL OR status NOT IN ('입실', '공실')
    """)
    cur.execute("""
        UPDATE business_room_inventory
           SET contract_end_date = NULL
         WHERE status = '공실'
    """)
    # 기존 방 재고는 장기방 노출이 가능했던 데이터로 보고 안전한 기본 채널로 보정한다.
    cur.execute("""
        UPDATE business_room_inventory
           SET channel = '장박가능'
         WHERE channel IS NULL OR channel NOT IN ('OTA전용', '장박가능')
    """)
    cur.execute(
        "ALTER TABLE business_room_inventory "
        "ALTER COLUMN status SET DEFAULT '공실'"
    )
    cur.execute(
        "ALTER TABLE business_room_inventory "
        "ALTER COLUMN status SET NOT NULL"
    )
    cur.execute(
        "ALTER TABLE business_room_inventory "
        "ALTER COLUMN channel SET DEFAULT '장박가능'"
    )
    cur.execute(
        "ALTER TABLE business_room_inventory "
        "ALTER COLUMN channel SET NOT NULL"
    )
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                 WHERE conname = 'business_room_inventory_status_check'
                   AND conrelid = 'business_room_inventory'::regclass
            ) THEN
                ALTER TABLE business_room_inventory
                ADD CONSTRAINT business_room_inventory_status_check
                CHECK (status IN ('입실', '공실'));
            END IF;
        END $$;
    """)
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                 WHERE conname = 'business_room_inventory_channel_check'
                   AND conrelid = 'business_room_inventory'::regclass
            ) THEN
                ALTER TABLE business_room_inventory
                ADD CONSTRAINT business_room_inventory_channel_check
                CHECK (channel IN ('OTA전용', '장박가능'));
            END IF;
        END $$;
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS ix_business_room_inventory_listing "
        "ON business_room_inventory(listing_request_id, id)"
    )
    # 직거래 매물 사진 (등록자가 첨부, 공개 표시)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS listing_photos (
            id SERIAL PRIMARY KEY,
            listing_request_id INTEGER NOT NULL REFERENCES listing_requests(id) ON DELETE CASCADE,
            image_key TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            is_public BOOLEAN,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("ALTER TABLE listing_photos ADD COLUMN IF NOT EXISTS is_public BOOLEAN")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_listing_photos_lr ON listing_photos(listing_request_id, sort_order)")

    # 직거래 매물 찜(♥) — 사용자별 중복 방지 unique constraint
    cur.execute("""
        CREATE TABLE IF NOT EXISTS listing_likes (
            id SERIAL PRIMARY KEY,
            listing_request_id INTEGER NOT NULL REFERENCES listing_requests(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE(listing_request_id, user_id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_listing_likes_lr ON listing_likes(listing_request_id)")

    # 매물의뢰 이력 — 접수/수정/철회 변경 내역을 타임라인으로 보존
    cur.execute("""
        CREATE TABLE IF NOT EXISTS listing_request_history (
            id SERIAL PRIMARY KEY,
            listing_request_id INTEGER NOT NULL REFERENCES listing_requests(id),
            action VARCHAR(20) NOT NULL,   -- 'created' | 'edited' | 'withdrawn'
            before_data JSONB,
            after_data JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)

    # 직거래 채팅방 — 매수자↔매도자 인앱 메시지
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_rooms (
            id SERIAL PRIMARY KEY,
            listing_request_id INTEGER NOT NULL REFERENCES listing_requests(id),
            buyer_user_id  INTEGER REFERENCES users(id),
            seller_user_id INTEGER NOT NULL REFERENCES users(id),
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (listing_request_id, buyer_user_id)
        )
    """)
    # 채팅목록(GET /api/chat/rooms) — 참여자 기준 조회용 인덱스
    cur.execute("CREATE INDEX IF NOT EXISTS ix_chat_rooms_buyer ON chat_rooms(buyer_user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_chat_rooms_seller ON chat_rooms(seller_user_id)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id SERIAL PRIMARY KEY,
            room_id INTEGER NOT NULL REFERENCES chat_rooms(id),
            sender_user_id INTEGER NOT NULL REFERENCES users(id),
            body TEXT NOT NULL,
            is_read BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_chat_messages_room ON chat_messages(room_id, created_at)")
    # 기존 테이블에 컬럼 추가 (이미 있으면 무시)
    cur.execute("""
        ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS is_read BOOLEAN NOT NULL DEFAULT FALSE
    """)
    cur.execute("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS attachment_key TEXT")
    cur.execute("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS attachment_name TEXT")

    # 대출상담 신청 (일반회원 → 대출상담사 라우팅)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS loan_consult_requests (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            master_building_id INTEGER NOT NULL REFERENCES master_buildings(id),
            message TEXT,
            contact_phone TEXT NOT NULL,
            routed_consultant_id INTEGER REFERENCES loan_consultants(id),
            routed_reason TEXT,              -- exclusive | region
            status TEXT DEFAULT 'submitted', -- submitted | in_progress | done
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    # 운영업체 상담 신청 (일반회원 → 운영업체 라우팅, 업종 필터 필수)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS operator_consult_requests (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            master_building_id INTEGER NOT NULL REFERENCES master_buildings(id),
            category TEXT NOT NULL,
            message TEXT,
            contact_phone TEXT NOT NULL,
            routed_operator_id INTEGER REFERENCES operators(id),
            routed_reason TEXT,              -- exclusive | region
            status TEXT DEFAULT 'submitted',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # 매수의뢰(일반 회원 → 중개사 라우팅) — listing_requests와 동일 구조, 매수자 측 요청.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS buy_requests (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        master_building_id INTEGER NOT NULL REFERENCES master_buildings(id),
        deal_type TEXT NOT NULL,
        desired_price TEXT,
        price_krw INTEGER,
        monthly_rent_krw INTEGER,
        contact_phone TEXT NOT NULL,
        routed_agent_id INTEGER REFERENCES agents(id),
        routed_reason TEXT,
        status TEXT DEFAULT 'submitted',
        admin_note TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """)

    # 전국공인중개사사무소 표준데이터 수집본 — 인근 중개업소 후보 및 주소 매칭용.
    # 공공데이터포털 API는 원본 등록번호를 reg_number에 저장한다.
    # V-World D171은 원본 등록번호 충돌을 보존하기 위해 reg_number에 결정적 내부키를,
    # source_reg_number에 화면 표시용 원본 번호를 저장한다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS broker_registry (
        id SERIAL PRIMARY KEY,
        office_name TEXT NOT NULL,         -- 사무소명
        reg_number TEXT NOT NULL UNIQUE,   -- 개설등록번호
        road_address TEXT,                 -- 소재지도로명주소
        jibun_address TEXT,                -- 소재지지번주소
        phone TEXT,                        -- 전화번호
        reg_date TEXT,                     -- 개설등록일자 (YYYY-MM-DD)
        owner_name TEXT,                   -- 대표자명
        lat DOUBLE PRECISION,              -- 위도
        lng DOUBLE PRECISION,              -- 경도
        homepage_url TEXT,                 -- 홈페이지주소
        biz_status TEXT,                   -- 영업상태 (현재 개업 표준데이터는 영업중으로 저장)
        source_updated_at TEXT,            -- 데이터기준일자
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_broker_registry_latlng ON broker_registry(lat, lng)")
    cur.execute("ALTER TABLE broker_registry ADD COLUMN IF NOT EXISTS road_norm TEXT")
    cur.execute("ALTER TABLE broker_registry ADD COLUMN IF NOT EXISTS jibun_norm TEXT")
    cur.execute("ALTER TABLE broker_registry ADD COLUMN IF NOT EXISTS biz_status TEXT")
    cur.execute("ALTER TABLE broker_registry ADD COLUMN IF NOT EXISTS source_reg_number TEXT")
    cur.execute("ALTER TABLE broker_registry ADD COLUMN IF NOT EXISTS source_region_code TEXT")
    cur.execute("ALTER TABLE broker_registry ADD COLUMN IF NOT EXISTS source_name TEXT")
    cur.execute("ALTER TABLE broker_registry ADD COLUMN IF NOT EXISTS phone_numbers TEXT[] NOT NULL DEFAULT '{}'")
    cur.execute("ALTER TABLE broker_registry ADD COLUMN IF NOT EXISTS member_count INTEGER NOT NULL DEFAULT 0")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_broker_registry_road_norm ON broker_registry(road_norm)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_broker_registry_jibun_norm ON broker_registry(jibun_norm)")
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_broker_registry_source_reg
        ON broker_registry(source_region_code, source_reg_number)
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS broker_registry_members (
            id SERIAL PRIMARY KEY,
            source_row_key TEXT NOT NULL UNIQUE,
            source_name TEXT NOT NULL,
            region_code TEXT,
            region_name TEXT,
            reg_number TEXT NOT NULL,
            office_name TEXT,
            member_name TEXT,
            member_type_code TEXT,
            member_type_name TEXT,
            license_number TEXT,
            license_date TEXT,
            position_code TEXT,
            position_name TEXT,
            source_updated_at TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_broker_registry_members_office
        ON broker_registry_members(region_code, reg_number, office_name)
    """)

    # 행안부 '문화_숙박업 조회서비스'(apis.data.go.kr/1741000/lodgings/info) 수집본.
    # 수집은 sync_lodgings.py — 실제 API 업태명 기준 생활숙박·일반숙박을 저장. permit_number(관리번호) 유일키 UPSERT.
    # road_norm: 도로명주소 정규화(도로명+건물번호 prefix) — master_buildings 주소 매칭용.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS lodging_registry (
        id SERIAL PRIMARY KEY,
        biz_name TEXT NOT NULL,            -- 사업장명 (BPLC_NM)
        permit_number TEXT NOT NULL UNIQUE,-- 관리번호 (MNG_NO)
        road_address TEXT,                 -- 도로명주소 (ROAD_NM_ADDR)
        jibun_address TEXT,                -- 지번주소 (LOTNO_ADDR)
        permit_date TEXT,                  -- 인허가일자 (LCPMT_YMD)
        biz_status_name TEXT,              -- 영업상태명 (SALS_STTS_NM: 영업/정상, 폐업 등)
        biz_status_detail TEXT,            -- 상세영업상태명 (DTL_SALS_STTS_NM)
        room_count INTEGER,                -- 객실수 = 한실(KSRM_CNT)+양실(WSRM_CNT)
        hygiene_type TEXT,                 -- 위생업태명 (SNTTN_BZSTAT_NM)
        phone TEXT,                        -- 전화번호 (TELNO)
        road_norm TEXT,                    -- 정규화 주소(도로명+건물번호)
        jibun_norm TEXT,                   -- 정규화 지번주소(동/읍/면+번지) — 도로명 매칭 실패 시 2차 매칭용
        biz_name_norm TEXT,                -- 정규화 사업장명 (operators 매칭용)
        source_updated_at TEXT,            -- 데이터갱신일자 (DAT_UPDT_PNT)
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )
    """)
    cur.execute("ALTER TABLE lodging_registry ADD COLUMN IF NOT EXISTS jibun_norm TEXT")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lodging_registry_road_norm ON lodging_registry(road_norm)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lodging_registry_jibun_norm ON lodging_registry(jibun_norm)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lodging_registry_status ON lodging_registry(biz_status_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lodging_registry_name_norm ON lodging_registry(biz_name_norm)")
    cur.execute("ALTER TABLE lodging_registry ADD COLUMN IF NOT EXISTS applied_building_id INTEGER REFERENCES master_buildings(id)")
    cur.execute("ALTER TABLE lodging_registry ADD COLUMN IF NOT EXISTS dismissed_at TIMESTAMP")

    # 로그인 회원의 관심단지 — 프론트 localStorage favKey(building_name|address)와 동일 규칙으로 저장.
    #   - building_name: 매칭 성공 시 건물명. 미매칭 거래는 NULL(프론트 favKey의 "null"과 대응).
    #   - (user_id, building_name, address) 조합은 유일(중복 저장 방지). NULL 비교 이슈를 피하려고
    #     COALESCE(building_name,'') 를 쓰는 표현식 UNIQUE 인덱스로 부여한다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_favorites (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        building_name TEXT,                -- 매칭 성공 시 건물명, 미매칭이면 NULL
        address TEXT NOT NULL,             -- 법정동+지번 조합 표시용 주소 (transactions.address와 동일)
        created_at TIMESTAMP DEFAULT NOW()
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_favorites_user ON user_favorites(user_id)")
    # 관심저장 시점에 프론트가 알고 있는 master_buildings.id를 직접 저장 —
    # 실거래가 없는 건물도 마이페이지/홈 위젯에서 상세 링크가 끊기지 않게 한다.
    cur.execute("ALTER TABLE user_favorites ADD COLUMN IF NOT EXISTS master_building_id INTEGER")
    # 관심단지 저장과 독립적인 급매 알림 토글. 기존 관심단지는 기본적으로 꺼져 있다.
    cur.execute(
        "ALTER TABLE user_favorites ADD COLUMN IF NOT EXISTS urgent_alert_enabled BOOLEAN NOT NULL DEFAULT FALSE"
    )
    # 숙박알리미의 추가 신호. 기존 관심단지는 명시적으로 켜기 전까지 구독하지 않는다.
    cur.execute(
        "ALTER TABLE user_favorites ADD COLUMN IF NOT EXISTS new_listing_alert_enabled BOOLEAN NOT NULL DEFAULT FALSE"
    )
    cur.execute(
        "ALTER TABLE user_favorites ADD COLUMN IF NOT EXISTS permit_change_alert_enabled BOOLEAN NOT NULL DEFAULT FALSE"
    )
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_favorites "
        "ON user_favorites (user_id, COALESCE(building_name, ''), address)"
    )
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_favorites_urgent_alert
        ON user_favorites(master_building_id)
        WHERE urgent_alert_enabled = TRUE AND master_building_id IS NOT NULL
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_favorites_new_listing_alert
        ON user_favorites(master_building_id)
        WHERE new_listing_alert_enabled = TRUE AND master_building_id IS NOT NULL
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_favorites_permit_change_alert
        ON user_favorites(master_building_id)
        WHERE permit_change_alert_enabled = TRUE AND master_building_id IS NOT NULL
    """)

    # 실거래 알림 구독 — user_favorites 와 구조는 같지만 별도 테이블(관심저장과 독립적으로
    # 켜고 끌 수 있어야 함). 새 실거래가 들어오면 sync_batch 가 이 구독을 조회해 notifications 를 만든다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_alert_subscriptions (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        building_name TEXT,                -- 매칭 성공 시 건물명, 미매칭이면 NULL
        address TEXT NOT NULL,             -- transactions.address 와 동일 규칙(법정동+지번)
        created_at TIMESTAMP DEFAULT NOW()
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_alert_subs_user ON user_alert_subscriptions(user_id)")
    # 새 실거래 매칭 조회용(주소+건물명) 인덱스
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_alert_subs_match ON user_alert_subscriptions(address)")
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_alert_subs "
        "ON user_alert_subscriptions (user_id, COALESCE(building_name, ''), address)"
    )

    # 일일 관심단지 실거래 이메일 발송 이력 — 같은 회원·거래·KST 날짜의 재발송 방지.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS deal_alert_logs (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
        alert_date DATE NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        claimed_at TIMESTAMP DEFAULT NOW(),
        sent_at TIMESTAMP,
        error_message TEXT,
        UNIQUE (user_id, transaction_id, alert_date)
    )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_deal_alert_logs_user_date
        ON deal_alert_logs (user_id, alert_date)
    """)

    # 알림함 — 새 실거래 발생 시 구독자별로 1건씩 쌓인다. 헤더 벨 아이콘이 읽어간다.
    #   transaction_id: 어떤 실거래로 만든 알림인지(같은 거래로 같은 사용자에게 중복 생성 방지).
    cur.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        body TEXT,
        building_name TEXT,
        address TEXT,
        transaction_id INTEGER,            -- 원본 실거래 id (수동 생성 알림이면 NULL)
        listing_request_id INTEGER REFERENCES listing_requests(id) ON DELETE CASCADE,
        is_read BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """)
    cur.execute(
        "ALTER TABLE notifications "
        "ADD COLUMN IF NOT EXISTS listing_request_id INTEGER REFERENCES listing_requests(id) ON DELETE CASCADE"
    )
    cur.execute(
        "ALTER TABLE notifications "
        "ADD COLUMN IF NOT EXISTS master_building_id INTEGER REFERENCES master_buildings(id) ON DELETE SET NULL"
    )
    # 헤더 벨: 안읽음 우선 + 최신순 조회용 인덱스
    cur.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read, created_at DESC)")
    # 같은 거래로 같은 사용자에게 알림 중복 생성 방지.
    #   transaction_id 가 NULL(수동 생성)인 행은 Postgres 에서 NULL 끼리 서로 다르게 취급되어
    #   유니크 제약에 걸리지 않는다 → 전체 유니크 인덱스로 둬도 문제없음(부분 인덱스면 ON CONFLICT 불가).
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_notifications_user_tx "
        "ON notifications (user_id, transaction_id)"
    )
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_notifications_user_listing "
        "ON notifications (user_id, listing_request_id)"
    )

    # 신규 급매 알림의 이메일 시도 이력 — 인앱 알림과 독립적으로 기록하며,
    # 같은 회원·같은 매물에는 이메일을 다시 시도하지 않는다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS urgent_listing_alert_logs (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        listing_request_id INTEGER NOT NULL REFERENCES listing_requests(id) ON DELETE CASCADE,
        notification_id INTEGER REFERENCES notifications(id) ON DELETE SET NULL,
        email_state TEXT NOT NULL DEFAULT 'pending',
        email_attempted_at TIMESTAMP,
        email_sent_at TIMESTAMP,
        email_error TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        UNIQUE (user_id, listing_request_id)
    )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_urgent_listing_alert_logs_listing
        ON urgent_listing_alert_logs(listing_request_id)
    """)
    cur.execute(
        "ALTER TABLE urgent_listing_alert_logs ADD COLUMN IF NOT EXISTS tier TEXT"
    )

    # 신규 공개 건물전체 매물 알림 — 급매 알림과 같은 매물에는 둘 중 하나만 예약한다.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS new_listing_alert_logs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            listing_request_id INTEGER NOT NULL REFERENCES listing_requests(id) ON DELETE CASCADE,
            notification_id INTEGER REFERENCES notifications(id) ON DELETE SET NULL,
            email_state TEXT NOT NULL DEFAULT 'pending',
            email_attempted_at TIMESTAMP,
            email_sent_at TIMESTAMP,
            email_error TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (user_id, listing_request_id)
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_new_listing_alert_logs_listing
        ON new_listing_alert_logs(listing_request_id)
    """)

    # 숙박업 동기화의 이전 상태. 최초 전체 수집에서는 이 테이블만 채우고 알림은 보내지 않는다.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lodging_registry_alert_snapshots (
            permit_number TEXT PRIMARY KEY,
            master_building_id INTEGER REFERENCES master_buildings(id) ON DELETE SET NULL,
            biz_status_name TEXT,
            biz_status_detail TEXT,
            room_count INTEGER,
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_lodging_alert_snapshots_building
        ON lodging_registry_alert_snapshots(master_building_id)
    """)

    # 건물별·KST 날짜별 신고변동 요약과 회원별 전달 상태를 분리한다.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS permit_change_alert_logs (
            id SERIAL PRIMARY KEY,
            master_building_id INTEGER NOT NULL REFERENCES master_buildings(id) ON DELETE CASCADE,
            change_date DATE NOT NULL,
            change_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
            delivery_queued_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (master_building_id, change_date)
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_permit_change_alert_logs_pending
        ON permit_change_alert_logs(change_date, delivery_queued_at)
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS permit_change_alert_deliveries (
            id SERIAL PRIMARY KEY,
            permit_change_alert_log_id INTEGER NOT NULL REFERENCES permit_change_alert_logs(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            notification_id INTEGER REFERENCES notifications(id) ON DELETE SET NULL,
            email_state TEXT NOT NULL DEFAULT 'pending',
            email_attempted_at TIMESTAMP,
            email_sent_at TIMESTAMP,
            email_error TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (permit_change_alert_log_id, user_id)
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_permit_change_alert_deliveries_user
        ON permit_change_alert_deliveries(user_id, created_at DESC)
    """)

    # 계약만기 알림 발송 이력 — 인앱/이메일 상태를 분리해 임계치별 중복을 막는다.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS room_expiry_alerts_sent (
            id SERIAL PRIMARY KEY,
            room_id INTEGER NOT NULL REFERENCES business_room_inventory(id) ON DELETE CASCADE,
            threshold TEXT NOT NULL,
            notification_id INTEGER REFERENCES notifications(id) ON DELETE SET NULL,
            in_app_sent_at TIMESTAMP,
            email_state TEXT NOT NULL DEFAULT 'pending',
            email_idempotency_key TEXT,
            email_attempted_at TIMESTAMP,
            email_sent_at TIMESTAMP,
            email_error TEXT,
            sent_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(room_id, threshold)
        )
    """)
    # 초기 버전의 RESTRICT FK/단일 sent_at 이력을 상태 분리 구조로 안전하게 보정한다.
    cur.execute("ALTER TABLE room_expiry_alerts_sent ADD COLUMN IF NOT EXISTS notification_id INTEGER")
    cur.execute("ALTER TABLE room_expiry_alerts_sent ADD COLUMN IF NOT EXISTS in_app_sent_at TIMESTAMP")
    cur.execute("ALTER TABLE room_expiry_alerts_sent ADD COLUMN IF NOT EXISTS email_state TEXT")
    cur.execute("ALTER TABLE room_expiry_alerts_sent ADD COLUMN IF NOT EXISTS email_idempotency_key TEXT")
    cur.execute("ALTER TABLE room_expiry_alerts_sent ADD COLUMN IF NOT EXISTS email_attempted_at TIMESTAMP")
    cur.execute("ALTER TABLE room_expiry_alerts_sent ADD COLUMN IF NOT EXISTS email_sent_at TIMESTAMP")
    cur.execute("ALTER TABLE room_expiry_alerts_sent ADD COLUMN IF NOT EXISTS email_error TEXT")
    cur.execute("""
        UPDATE room_expiry_alerts_sent
           SET in_app_sent_at = COALESCE(in_app_sent_at, sent_at),
               email_state = COALESCE(email_state, 'sent')
         WHERE in_app_sent_at IS NULL OR email_state IS NULL
    """)
    cur.execute("ALTER TABLE room_expiry_alerts_sent ALTER COLUMN email_state SET DEFAULT 'pending'")
    cur.execute("ALTER TABLE room_expiry_alerts_sent ALTER COLUMN email_state SET NOT NULL")
    cur.execute("ALTER TABLE room_expiry_alerts_sent DROP CONSTRAINT IF EXISTS room_expiry_alerts_sent_room_id_fkey")
    cur.execute("""
        ALTER TABLE room_expiry_alerts_sent
        ADD CONSTRAINT room_expiry_alerts_sent_room_id_fkey
        FOREIGN KEY (room_id) REFERENCES business_room_inventory(id) ON DELETE CASCADE
    """)
    cur.execute("ALTER TABLE room_expiry_alerts_sent DROP CONSTRAINT IF EXISTS room_expiry_alerts_sent_notification_id_fkey")
    cur.execute("""
        ALTER TABLE room_expiry_alerts_sent
        ADD CONSTRAINT room_expiry_alerts_sent_notification_id_fkey
        FOREIGN KEY (notification_id) REFERENCES notifications(id) ON DELETE SET NULL
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS ix_room_expiry_alerts_sent_room "
        "ON room_expiry_alerts_sent(room_id)"
    )
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_room_expiry_alert_email_key "
        "ON room_expiry_alerts_sent(email_idempotency_key) "
        "WHERE email_idempotency_key IS NOT NULL"
    )

    # 지자체(시군구)별 생활숙박시설 담당부서·연락처 (엑셀 원본 그대로 적재)
    # region_name_raw 는 가공하지 않은 엑셀 '지자체' 값 그대로 보존한다("진주시(중복)" 포함).
    # 매칭은 address_utils.match_authority_contact() 가 이 원본을 정규화해서 수행한다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS lodging_authority_contacts (
        id SERIAL PRIMARY KEY,
        region_name_raw TEXT NOT NULL,     -- 엑셀 '지자체' 원본 그대로
        dept TEXT,                         -- 담당부서
        phone TEXT,                        -- 전화번호
        created_at TIMESTAMP DEFAULT NOW()
    )
    """)

    # 공지사항 — 관리자가 등록하고 공개 페이지(/notices)가 읽는다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS notices (
        id SERIAL PRIMARY KEY,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        is_pinned BOOLEAN DEFAULT FALSE,     -- 상단 고정 여부 (고정글이 최신글보다 먼저 노출)
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )
    """)
    # 기존에 이미 만들어진 DB에도 안전하게 컬럼 추가 (데이터 보존)
    cur.execute("ALTER TABLE notices ADD COLUMN IF NOT EXISTS is_pinned BOOLEAN DEFAULT FALSE")
    cur.execute("ALTER TABLE notices ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()")
    cur.execute("ALTER TABLE notices ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW()")
    cur.execute("ALTER TABLE notices ADD COLUMN IF NOT EXISTS attachment_key TEXT")

    # 약관/개인정보처리방침 — 관리자가 admin.html에서 직접 수정하는 DB 기반 법적 문서.
    # doc_type은 'terms'(이용약관) 또는 'privacy'(개인정보처리방침) 두 값만 사용한다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS legal_documents (
        id SERIAL PRIMARY KEY,
        doc_type TEXT UNIQUE NOT NULL,       -- 'terms' | 'privacy'
        content TEXT NOT NULL,               -- 본문 (줄바꿈 포함 plain text 또는 간단한 HTML)
        updated_at TIMESTAMP DEFAULT NOW()
    )
    """)

    # 사이트 팝업/상단배너 — 관리자가 admin.html "팝업관리"에서 등록,
    # 공개 API(/api/popups/active)가 조건에 맞는 1건을 골라 header.js가 표시한다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS site_popups (
        id SERIAL PRIMARY KEY,
        title TEXT NOT NULL,                     -- 관리용 제목 (사용자에게는 미노출)
        start_at TIMESTAMP,                      -- 게재 시작 (NULL이면 즉시)
        end_at TIMESTAMP,                        -- 게재 종료 (NULL이면 무기한)
        show_desktop BOOLEAN DEFAULT TRUE,       -- 데스크톱 노출
        show_mobile BOOLEAN DEFAULT TRUE,        -- 모바일 노출
        scope TEXT DEFAULT 'all',                -- 'all'(전체 페이지) | 'home_only'(홈만)
        audience TEXT DEFAULT 'all',             -- 'all' | 'logged_in'(로그인 회원만)
        display_type TEXT DEFAULT 'popup',       -- 'popup'(모달) | 'top_banner'(상단배너)
        image_ref TEXT,                          -- Object Storage 참조 키 (popups/…)
        link_url TEXT,                           -- 클릭 시 이동 URL (없으면 링크 없음)
        open_new_tab BOOLEAN DEFAULT TRUE,       -- 링크 새 창 열기
        width_px INTEGER DEFAULT 400,            -- 팝업 너비(px)
        close_mode TEXT DEFAULT 'close',         -- 'close'(닫기만) | 'hide_today'(오늘 하루 안 보기)
        is_active BOOLEAN DEFAULT TRUE,          -- 게재중/중지 토글
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )
    """)

    # 앱 메타(키-값) — 관리 작업의 마지막 실행 기록 등 소소한 상태 저장용
    cur.execute("""
    CREATE TABLE IF NOT EXISTS app_meta (
        key TEXT PRIMARY KEY,               -- 예: 'geocode_last_run'
        value TEXT,                         -- 자유 형식(문자열/숫자)
        updated_at TIMESTAMP DEFAULT NOW()  -- 마지막 갱신 시각
    )
    """)

    # 중개사 의뢰 알림용 단축 링크 — 코드는 외부에 노출되므로 만료 시각을 함께 검증한다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS short_links (
        code VARCHAR(6) PRIMARY KEY,
        target_path TEXT NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        CONSTRAINT short_links_target_path_check
            CHECK (target_path LIKE '/admin%' OR target_path LIKE '/agent/dashboard%')
    )
    """)
    # 이전 단축 링크 스키마는 관리자 경로만 허용했다. 기존 테이블에도 중개사
    # 대시보드 딥링크를 저장할 수 있게 제약을 명시적으로 교체한다.
    cur.execute("ALTER TABLE short_links DROP CONSTRAINT IF EXISTS short_links_target_path_check")
    cur.execute("""
        ALTER TABLE short_links
        ADD CONSTRAINT short_links_target_path_check
        CHECK (target_path LIKE '/admin%' OR target_path LIKE '/agent/dashboard%')
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_short_links_expires_at
        ON short_links(expires_at)
    """)

    # 주간 이메일 기능 소개 시리즈. episode는 ISO 주차를 1~8회로 순환해 선택하는
    # 운영용 회차이며, 관리자가 내용을 바꾼 뒤에는 초기 시드가 덮어쓰지 않는다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS weekly_feature_tips (
        id SERIAL PRIMARY KEY,
        episode INTEGER NOT NULL UNIQUE CHECK (episode BETWEEN 1 AND 8),
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        cta_label TEXT NOT NULL DEFAULT '기능 자세히 보기',
        cta_url TEXT NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_weekly_feature_tips_active_episode
        ON weekly_feature_tips (is_active, episode)
    """)
    # ISO 주차는 1~8회차로 순환한다. 테이블을 최초 생성한 뒤 도입한 제약이라
    # 기존 환경에도 명시적으로 같은 범위를 적용한다.
    cur.execute("""
        ALTER TABLE weekly_feature_tips
        DROP CONSTRAINT IF EXISTS weekly_feature_tips_episode_check
    """)
    cur.execute("""
        ALTER TABLE weekly_feature_tips
        ADD CONSTRAINT weekly_feature_tips_episode_check
        CHECK (episode BETWEEN 1 AND 8)
    """)

    # 검색 성능을 위한 인덱스
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_deal_date ON transactions(deal_date DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_building_name ON transactions(building_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_address ON transactions(address)")
    # LATERAL 서브쿼리 최적화: 지도 마커 API가 건물마다 최근 실거래가를 조회할 때 사용
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_sgg_umd_jibun ON transactions(sgg_cd, umd_nm, jibun, deal_date DESC)")
    # 건물별 슬롯 조회(정원 충족 여부 확인)용 인덱스
    cur.execute("CREATE INDEX IF NOT EXISTS idx_slots_building ON slots(master_building_id)")
    # 건물별 매물 조회용 인덱스
    cur.execute("CREATE INDEX IF NOT EXISTS idx_listings_building ON listings(master_building_id)")
    # 통계(일별 방문 집계)용 인덱스
    cur.execute("CREATE INDEX IF NOT EXISTS idx_page_views_viewed_at ON page_views(viewed_at)")
    # 건물전체 매물 카드의 최근 5분 고유 열람자 집계용 인덱스
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_page_views_listing_recent "
        "ON page_views(listing_request_id, viewed_at DESC) "
        "WHERE listing_request_id IS NOT NULL"
    )
    # 공지사항 정렬(고정 우선 → 최신순)용 인덱스
    cur.execute("CREATE INDEX IF NOT EXISTS idx_notices_order ON notices(is_pinned DESC, created_at DESC)")
    # master_buildings 지번 복합 인덱스 — 지번 매칭 쿼리(transactions JOIN, nearby-stores 등) 최적화
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mb_sgg_umd_jibun ON master_buildings(sgg_cd, umd_nm, jibun)")

    # OTA 등록확인 (운영확인) — 1단계: 관리자 직접 입력
    # booking_url_source: 'admin'|'owner'|'operator'|'user_report' (1단계는 admin만 사용)
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS booking_url TEXT")
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS booking_url_source TEXT")
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS booking_url_updated_at TIMESTAMP")
    # OTA 링크 만료일 — 3단계(운영업체 신청) 승인 시 NOW()+3개월, 관리자 직접입력은 NULL(무기한)
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS booking_url_expires_at TIMESTAMP")

    # OTA 링크 신청 큐 — 위탁운영업체가 담당 건물의 OTA 링크를 신청; 관리자 승인 후 반영
    cur.execute("""
    CREATE TABLE IF NOT EXISTS booking_url_requests (
        id SERIAL PRIMARY KEY,
        operator_id INTEGER NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
        master_building_id INTEGER NOT NULL REFERENCES master_buildings(id) ON DELETE CASCADE,
        booking_url TEXT NOT NULL,
        status TEXT DEFAULT 'pending',   -- pending | approved | rejected | cancelled
        submitted_at TIMESTAMP DEFAULT NOW(),
        reviewed_at TIMESTAMP,
        reviewed_by INTEGER REFERENCES admin_users(id),
        admin_note TEXT
    )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_bur_operator
        ON booking_url_requests(operator_id, submitted_at DESC)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_bur_status
        ON booking_url_requests(status, submitted_at DESC)
    """)
    cur.execute("""
        ALTER TABLE booking_url_requests
        ADD COLUMN IF NOT EXISTS renewal_count INTEGER DEFAULT 0
    """)
    cur.execute("ALTER TABLE booking_url_requests ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP")

    # ── 사이트 오류신고 (플로팅 버튼 → 관리자 심사) ────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bug_reports (
            id           SERIAL PRIMARY KEY,
            user_id      INTEGER REFERENCES users(id),
            account_type TEXT,
            description  TEXT NOT NULL,
            page_url     TEXT,
            user_agent   TEXT,
            severity     TEXT DEFAULT 'annoying',
            contact      TEXT,
            screenshot_key TEXT,
            status       TEXT DEFAULT 'new',
            admin_note   TEXT,
            created_at   TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_bug_reports_status
        ON bug_reports(status, created_at DESC)
    """)

    # ── 상가정보 사전수집 캐시 (sync_stores.py → building_stores) ──────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS building_stores (
            id                 SERIAL PRIMARY KEY,
            master_building_id INTEGER NOT NULL REFERENCES master_buildings(id) ON DELETE CASCADE,
            store_name         TEXT,
            category           TEXT,
            floor              TEXT,
            ho_no              TEXT,
            inds_mcls_nm       TEXT,
            inds_scls_nm       TEXT,
            updated_at         TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_building_stores_building
        ON building_stores(master_building_id)
    """)

    # ── 전유부(호실별 전용면적) 온디맨드 캐시 ──────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS building_unit_areas (
            id                 SERIAL PRIMARY KEY,
            master_building_id INTEGER NOT NULL REFERENCES master_buildings(id) ON DELETE CASCADE,
            ho                 VARCHAR(20),
            area_sqm           NUMERIC,
            fetched_at         TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_unit_areas_building
        ON building_unit_areas(master_building_id)
    """)

    conn.commit()
    cur.close()
    conn.close()

    _ensure_raw_key_unique_constraint()
    _ensure_admin_email_unique_constraint()
    _ensure_agents_unique_constraints()
    _ensure_operators_unique_constraints()
    _ensure_loan_consultants_unique_constraints()
    _ensure_mileage_missions_code_unique_constraint()
    _ensure_users_unique_constraints()
    _seed_mileage_missions()
    _seed_admin_user()
    _seed_legal_documents()
    _seed_weekly_feature_tips()
    _normalize_umd_nm_spaces()
    _ensure_transaction_stats_indexes()

    # 전체 DDL/시드가 무사히 끝났을 때만 버전을 기록 → 다음 부팅부터 빠른 경로로 건너뜀
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO app_meta (key, value, updated_at) VALUES ('schema_version', %s, NOW())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
    """, (SCHEMA_VERSION,))
    conn.commit()
    cur.close()
    conn.close()
    print(f"스키마 버전 {SCHEMA_VERSION} 기록 완료 — 다음 부팅부터 DDL 건너뜀")


def _ensure_transaction_stats_indexes():
    """데이터랩 거래 통계용 인덱스를 서비스 중단 없이 보장한다."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        # CONCURRENTLY는 트랜잭션 블록 안에서 실행할 수 없으므로 별도 autocommit
        # 연결을 쓴다. 스키마 초기화 advisory lock은 중복 실행만 막는다.
        conn.autocommit = True
        cur.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_transactions_deal_date
            ON transactions (deal_date DESC)
        """)
        cur.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_transactions_building
            ON transactions (building_name, address)
        """)
    finally:
        cur.close()
        conn.close()


def _ensure_raw_key_unique_constraint():
    """
    raw_key에 DB 레벨 UNIQUE 제약을 안전하게 부여한다.
    CREATE TABLE IF NOT EXISTS로 예전에 이미 만들어진 테이블은 스키마에 UNIQUE가 적혀 있어도
    실제 테이블엔 반영 안 됐을 수 있어(IF NOT EXISTS는 이름만 봄) 별도로 확인/적용한다.
    1) 남아있는 중복 raw_key를 먼저 정리(가장 최근 id만 남김)
    2) 제약이 이미 있으면 건너뛰고, 없으면 추가
    """
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM transactions a USING transactions b
        WHERE a.raw_key = b.raw_key AND a.id < b.id
    """)
    deleted = cur.rowcount

    cur.execute("""
        SELECT tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_name = 'transactions'
          AND tc.constraint_type = 'UNIQUE'
          AND kcu.column_name = 'raw_key'
    """)
    exists = cur.fetchone()

    if not exists:
        cur.execute("""
            ALTER TABLE transactions
            ADD CONSTRAINT transactions_raw_key_unique UNIQUE (raw_key)
        """)
        print(f"raw_key UNIQUE 제약 신규 적용 완료 (중복 {deleted}건 사전 정리)")
    else:
        print(f"raw_key UNIQUE 제약 이미 존재({exists['constraint_name']}) — 중복 {deleted}건만 정리")

    conn.commit()
    cur.close()
    conn.close()


def _ensure_admin_email_unique_constraint():
    """
    admin_users.email에 DB 레벨 UNIQUE 제약을 안전하게 부여한다.
    (_ensure_raw_key_unique_constraint()와 같은 패턴)
    CREATE TABLE IF NOT EXISTS로 예전에 UNIQUE 없이 만들어진 테이블에도 확실히 반영되게 한다.
    1) 중복 email이 있는지 먼저 확인 — 있으면 계정을 함부로 지우지 않고(사용자 데이터 보호)
       경고만 출력하고 제약 부여를 건너뛴다 (raw_key와 달리 자동 삭제하지 않음).
    2) 제약이 이미 있으면 건너뛰고, 없으면 추가.
    """
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT LOWER(email) AS email_l, COUNT(*) AS c
        FROM admin_users
        GROUP BY LOWER(email)
        HAVING COUNT(*) > 1
    """)
    dups = cur.fetchall()

    cur.execute("""
        SELECT tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_name = 'admin_users'
          AND tc.constraint_type = 'UNIQUE'
          AND kcu.column_name = 'email'
    """)
    exists = cur.fetchone()

    if exists:
        print(f"admin_users.email UNIQUE 제약 이미 존재({exists['constraint_name']})")
    elif dups:
        print(f"[경고] admin_users.email 중복 {len(dups)}건 발견 — 계정 자동 삭제하지 않고 UNIQUE 제약 부여를 건너뜁니다. 수동 정리 후 재실행하세요.")
    else:
        cur.execute("""
            ALTER TABLE admin_users
            ADD CONSTRAINT admin_users_email_unique UNIQUE (email)
        """)
        print("admin_users.email UNIQUE 제약 신규 적용 완료")

    conn.commit()
    cur.close()
    conn.close()


def _ensure_agents_unique_constraints():
    """
    agents.reg_number, agents.subdomain_slug에 DB 레벨 UNIQUE 제약을 안전하게 부여한다.
    (_ensure_admin_email_unique_constraint()와 같은 패턴)
    - 중복 값이 있으면 계정/신청 데이터를 함부로 지우지 않고 경고만 출력하고 건너뛴다.
    - 제약이 이미 있으면 skip, 없으면 add. (재실행 안전)
    - subdomain_slug는 NULL 허용(미승인 상태)이며, PostgreSQL UNIQUE는 NULL 다중 허용이라 문제 없음.
    """
    conn = get_conn()
    cur = conn.cursor()

    targets = [
        ("reg_number", "agents_reg_number_unique"),
        ("subdomain_slug", "agents_subdomain_slug_unique"),
    ]
    for column, constraint_name in targets:
        cur.execute(f"""
            SELECT {column} AS v, COUNT(*) AS c
            FROM agents
            WHERE {column} IS NOT NULL
            GROUP BY {column}
            HAVING COUNT(*) > 1
        """)
        dups = cur.fetchall()

        cur.execute("""
            SELECT tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_name = 'agents'
              AND tc.constraint_type = 'UNIQUE'
              AND kcu.column_name = %s
        """, (column,))
        exists = cur.fetchone()

        if exists:
            print(f"agents.{column} UNIQUE 제약 이미 존재({exists['constraint_name']})")
        elif dups:
            print(f"[경고] agents.{column} 중복 {len(dups)}건 발견 — 데이터 자동 삭제하지 않고 UNIQUE 제약 부여를 건너뜁니다. 수동 정리 후 재실행하세요.")
        else:
            cur.execute(f"ALTER TABLE agents ADD CONSTRAINT {constraint_name} UNIQUE ({column})")
            print(f"agents.{column} UNIQUE 제약 신규 적용 완료")

    conn.commit()
    cur.close()
    conn.close()


def _ensure_operators_unique_constraints():
    """
    operators.subdomain_slug에 DB 레벨 UNIQUE 제약을 안전하게 부여한다.
    (_ensure_agents_unique_constraints()와 같은 패턴)
    - 중복 값이 있으면 데이터를 지우지 않고 경고만 출력하고 건너뛴다.
    - 제약이 이미 있으면 skip, 없으면 add. (재실행 안전)
    - subdomain_slug는 NULL 허용(미승인 상태)이며, PostgreSQL UNIQUE는 NULL 다중 허용이라 문제 없음.
    """
    conn = get_conn()
    cur = conn.cursor()

    targets = [
        ("subdomain_slug", "operators_subdomain_slug_unique"),
    ]
    for column, constraint_name in targets:
        cur.execute(f"""
            SELECT {column} AS v, COUNT(*) AS c
            FROM operators
            WHERE {column} IS NOT NULL
            GROUP BY {column}
            HAVING COUNT(*) > 1
        """)
        dups = cur.fetchall()

        cur.execute("""
            SELECT tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_name = 'operators'
              AND tc.constraint_type = 'UNIQUE'
              AND kcu.column_name = %s
        """, (column,))
        exists = cur.fetchone()

        if exists:
            print(f"operators.{column} UNIQUE 제약 이미 존재({exists['constraint_name']})")
        elif dups:
            print(f"[경고] operators.{column} 중복 {len(dups)}건 발견 — 데이터 자동 삭제하지 않고 UNIQUE 제약 부여를 건너뜁니다. 수동 정리 후 재실행하세요.")
        else:
            cur.execute(f"ALTER TABLE operators ADD CONSTRAINT {constraint_name} UNIQUE ({column})")
            print(f"operators.{column} UNIQUE 제약 신규 적용 완료")

    conn.commit()
    cur.close()
    conn.close()


def _ensure_loan_consultants_unique_constraints():
    """
    loan_consultants.license_number, loan_consultants.subdomain_slug, loan_consultants.email에
    DB 레벨 UNIQUE 제약을 안전하게 부여한다. (_ensure_agents_unique_constraints()와 같은 패턴)
    - 중복 값이 있으면 데이터를 지우지 않고 경고만 출력하고 건너뛴다.
    - 제약이 이미 있으면 skip, 없으면 add. (재실행 안전)
    - email은 대소문자 무시(LOWER)로 중복 확인.
    """
    conn = get_conn()
    cur = conn.cursor()

    targets = [
        ("license_number", "license_number", "loan_consultants_license_number_unique"),
        ("subdomain_slug", "subdomain_slug", "loan_consultants_subdomain_slug_unique"),
        ("email", "LOWER(email)", "loan_consultants_email_unique"),
    ]
    for column, dup_expr, constraint_name in targets:
        cur.execute(f"""
            SELECT {dup_expr} AS v, COUNT(*) AS c
            FROM loan_consultants
            WHERE {column} IS NOT NULL
            GROUP BY {dup_expr}
            HAVING COUNT(*) > 1
        """)
        dups = cur.fetchall()

        cur.execute("""
            SELECT tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_name = 'loan_consultants'
              AND tc.constraint_type = 'UNIQUE'
              AND kcu.column_name = %s
        """, (column,))
        exists = cur.fetchone()

        if exists:
            print(f"loan_consultants.{column} UNIQUE 제약 이미 존재({exists['constraint_name']})")
        elif dups:
            print(f"[경고] loan_consultants.{column} 중복 {len(dups)}건 발견 — 데이터 자동 삭제하지 않고 UNIQUE 제약 부여를 건너뜁니다. 수동 정리 후 재실행하세요.")
        else:
            cur.execute(f"ALTER TABLE loan_consultants ADD CONSTRAINT {constraint_name} UNIQUE ({column})")
            print(f"loan_consultants.{column} UNIQUE 제약 신규 적용 완료")

    conn.commit()
    cur.close()
    conn.close()


def _ensure_users_unique_constraints():
    """
    users.email, users.kakao_id에 DB 레벨 UNIQUE 제약을 안전하게 부여한다.
    (_ensure_agents_unique_constraints()와 같은 패턴)
    - 중복 값이 있으면 회원 계정을 함부로 지우지 않고(사용자 데이터 보호) 경고만 출력하고 건너뛴다.
    - 제약이 이미 있으면 skip, 없으면 add. (재실행 안전)
    - email은 대소문자 무시 중복 확인(LOWER). kakao_id는 NULL 허용이며 PostgreSQL UNIQUE는 NULL 다중 허용이라 문제 없음.
      (이메일 가입자는 kakao_id가 NULL이라 서로 충돌하지 않음)
    """
    conn = get_conn()
    cur = conn.cursor()

    targets = [
        ("email", "LOWER(email)", "users_email_unique", "email"),
        ("kakao_id", "kakao_id", "users_kakao_id_unique", "kakao_id"),
    ]
    for label, dup_expr, constraint_name, column in targets:
        cur.execute(f"""
            SELECT {dup_expr} AS v, COUNT(*) AS c
            FROM users
            WHERE {column} IS NOT NULL
            GROUP BY {dup_expr}
            HAVING COUNT(*) > 1
        """)
        dups = cur.fetchall()

        cur.execute("""
            SELECT tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_name = 'users'
              AND tc.constraint_type = 'UNIQUE'
              AND kcu.column_name = %s
        """, (column,))
        exists = cur.fetchone()

        if exists:
            print(f"users.{label} UNIQUE 제약 이미 존재({exists['constraint_name']})")
        elif dups:
            print(f"[경고] users.{label} 중복 {len(dups)}건 발견 — 계정 자동 삭제하지 않고 UNIQUE 제약 부여를 건너뜁니다. 수동 정리 후 재실행하세요.")
        else:
            cur.execute(f"ALTER TABLE users ADD CONSTRAINT {constraint_name} UNIQUE ({column})")
            print(f"users.{label} UNIQUE 제약 신규 적용 완료")

    conn.commit()
    cur.close()
    conn.close()


def _ensure_mileage_missions_code_unique_constraint():
    """
    mileage_missions.code에 DB 레벨 UNIQUE 제약을 안전하게 부여한다.
    (_ensure_agents_unique_constraints()와 같은 패턴)
    - 중복 code가 있으면 정책 데이터를 함부로 지우지 않고 경고만 출력하고 건너뛴다.
    - 제약이 이미 있으면 skip, 없으면 add. (재실행 안전)
    - 이 제약은 _seed_mileage_missions()의 ON CONFLICT (code) 동작에 필요하므로 시드보다 먼저 실행된다.
    """
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT code, COUNT(*) AS c
        FROM mileage_missions
        WHERE code IS NOT NULL
        GROUP BY code
        HAVING COUNT(*) > 1
    """)
    dups = cur.fetchall()

    cur.execute("""
        SELECT tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_name = 'mileage_missions'
          AND tc.constraint_type = 'UNIQUE'
          AND kcu.column_name = 'code'
    """)
    exists = cur.fetchone()

    if exists:
        print(f"mileage_missions.code UNIQUE 제약 이미 존재({exists['constraint_name']})")
    elif dups:
        print(f"[경고] mileage_missions.code 중복 {len(dups)}건 발견 — 데이터 자동 삭제하지 않고 UNIQUE 제약 부여를 건너뜁니다. 수동 정리 후 재실행하세요.")
    else:
        cur.execute("ALTER TABLE mileage_missions ADD CONSTRAINT mileage_missions_code_unique UNIQUE (code)")
        print("mileage_missions.code UNIQUE 제약 신규 적용 완료")

    conn.commit()
    cur.close()
    conn.close()


def _seed_mileage_missions():
    """
    미션 정의(정책 테이블) 초기 데이터를 삽입한다.
    - code 기준 ON CONFLICT DO NOTHING이라 이미 있으면 중복 삽입되지 않는다 (재실행 안전).
    - ON CONFLICT (code)는 code UNIQUE 제약이 있어야 동작한다. 보통은
      _ensure_mileage_missions_code_unique_constraint()에서 미리 걸리지만,
      레거시 중복 데이터 때문에 제약 부여가 건너뛰어졌을 수 있으므로 여기서도
      제약 존재를 먼저 확인하고, 없으면 시드를 안전하게 건너뛴다(에러로 init_db 중단 방지).
    """
    missions = [
        ("photo_exterior", "건물 외관 사진", 20, "basic"),
        ("photo_building_id", "건축물 표시(문패·집합건축물대장 확인용)", 20, "basic"),
        ("gps_tag", "GPS 좌표 태깅", 10, "basic"),
        ("operation_type_check", "운영 형태 확인", 15, "basic"),
        ("management_office_info", "관리사무소·법인 안내판", 10, "basic"),
        ("surroundings_memo", "주변 환경 메모", 5, "basic"),
        ("admin_consent", "건물 관리자 개인정보 이용동의 수집", 150, "top"),
        ("biz_license_confirm", "숙박업 영업신고증 확인", 220, "top2"),
    ]
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT 1
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_name = 'mileage_missions'
          AND tc.constraint_type = 'UNIQUE'
          AND kcu.column_name = 'code'
    """)
    if not cur.fetchone():
        print("[경고] mileage_missions.code UNIQUE 제약이 없어 시드를 건너뜁니다. code 중복 정리 후 재실행하세요.")
        cur.close()
        conn.close()
        return

    cur.executemany("""
        INSERT INTO mileage_missions (code, title, points, tier)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (code) DO NOTHING
    """, missions)
    inserted = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    print(f"mileage_missions 시드 완료 (신규 {inserted}건 삽입, 총 {len(missions)}건 정의)")


def _seed_admin_user():
    """
    최초 관리자 계정 1건을 시드한다 (email='ADMIN' / password='ADMIN').
    - admin_users에 행이 하나라도 있으면 아무것도 하지 않는다(기존 계정 절대 덮어쓰기 금지).
    - 완전히 비어 있을 때만 딱 1건 생성한다 (재실행 안전).
    - 초기 비밀번호는 반드시 로그인 후 '비밀번호 변경'으로 교체하도록 안내한다.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        # WHERE NOT EXISTS로 "테이블이 완전히 비었을 때만" 원자적으로 1건 삽입한다.
        # (동시 초기화 시에도 경쟁 상태 없이 안전 — 이미 행이 있으면 0건 삽입)
        cur.execute(
            """INSERT INTO admin_users (email, password_hash, name, role)
               SELECT %s, %s, %s, %s
               WHERE NOT EXISTS (SELECT 1 FROM admin_users)""",
            ("ADMIN", generate_password_hash("ADMIN"), "관리자", "super_admin"),
        )
        conn.commit()
        if cur.rowcount:
            print("admin_users 초기 계정 시드 완료 (email='ADMIN' / 초기 비밀번호 'ADMIN' — 로그인 후 반드시 변경하세요)")
    finally:
        cur.close()
        conn.close()


_LEGAL_TERMS_SEED = """<h2>제1조 (목적)</h2>
<p>이 약관은 빌드리머스(이하 "회사")가 제공하는 생활숙박시설·분양형호텔·콘도 실거래가 조회 서비스(이하 "서비스")의 이용과 관련하여 회사와 이용자 간의 권리, 의무 및 책임사항을 규정함을 목적으로 합니다.</p>

<h2>제2조 (정의)</h2>
<ul>
<li>"서비스"란 회사가 제공하는 전국 생활숙박시설 등의 실거래가 정보 조회 및 관련 부가 서비스를 말합니다.</li>
<li>"이용자"란 이 약관에 따라 회사가 제공하는 서비스를 이용하는 회원 및 비회원을 말합니다.</li>
<li>"회원"이란 회사에 개인정보를 제공하여 회원등록을 한 자로서, 서비스를 지속적으로 이용할 수 있는 자를 말합니다.</li>
</ul>

<h2>제2조의2 (파트너 회원)</h2>
<p>"파트너 회원"이란 회사가 정한 승인 절차를 거쳐 중개사, 운영지원업체, 대출상담사로 등록된 회원을 말합니다. 파트너 회원에게는 일반 회원과 다른 별도의 이용조건이 적용될 수 있습니다.</p>

<h2>제3조 (약관의 효력 및 변경)</h2>
<p>이 약관은 서비스 화면에 게시하거나 기타의 방법으로 이용자에게 공지함으로써 효력이 발생합니다. 회사는 관련 법령을 위배하지 않는 범위에서 이 약관을 변경할 수 있으며, 변경된 약관은 공지와 동시에 효력이 발생합니다.</p>

<h2>제4조 (서비스의 제공)</h2>
<p>회사는 국토교통부 실거래가 공개시스템 등 공공데이터를 기반으로 실거래가 정보를 제공합니다. 제공되는 정보는 참고용이며, 실제 거래 시점의 가격 및 조건과 다를 수 있습니다. 회사는 정보의 정확성·완전성을 보장하지 않으며, 이를 근거로 한 이용자의 판단과 그 결과에 대해 책임지지 않습니다.</p>

<h2>제4조의2 (파트너 서비스 및 정보 연결)</h2>
<p>① 회사는 이용자와 파트너 회원 간의 정보 연결(매물의뢰 자동배정 등)을 제공할 뿐, 회사 스스로 부동산 중개행위, 위탁운영 계약, 대출 중개·모집 행위를 직접 수행하지 않습니다.</p>
<p>② 회사는 파트너 회원의 자격 서류(사업자등록증, 중개사무소 등록증, 대출모집인 등록번호 등)를 확인 절차를 거쳐 승인하나, 이는 서류상 확인 절차일 뿐 파트너 회원의 실제 자격 유지, 서비스 품질, 상담·거래 결과를 보증하는 것이 아닙니다.</p>
<p>③ 이용자와 파트너 회원 간에 체결되는 계약(중개계약, 위탁운영계약, 대출상담 등)은 이용자와 파트너 회원 간의 직접 계약이며, 회사는 그 계약의 당사자가 아닙니다.</p>

<h2>제5조 (이용자의 의무)</h2>
<ul>
<li>이용자는 서비스를 이용함에 있어 관련 법령 및 이 약관의 규정을 준수하여야 합니다.</li>
<li>이용자는 서비스에서 제공하는 정보를 회사의 사전 동의 없이 영리 목적으로 복제·배포·가공하여서는 안 됩니다.</li>
<li>이용자는 서비스의 안정적 운영을 방해하는 행위를 하여서는 안 됩니다.</li>
</ul>

<h2>제5조의2 (파트너 회원의 의무)</h2>
<p>① 파트너 회원은 신청 시 제출한 정보 및 서류가 진실함을 보증하며, 허위 서류 제출이 확인되는 경우 회사는 사전 통지 없이 승인을 취소하고 서비스 이용을 제한할 수 있습니다.</p>
<p>② 파트너 회원은 관계 법령(공인중개사법, 금융소비자보호법 등)을 준수하여야 하며, 이를 위반하여 발생한 손해에 대해서는 파트너 회원 본인이 책임을 집니다.</p>

<h2>제6조 (면책조항)</h2>
<p>회사는 천재지변, 공공데이터 제공기관의 사정, 기타 불가항력으로 인하여 서비스를 제공할 수 없는 경우 그 책임이 면제됩니다. 회사는 이용자가 서비스에 게재한 정보·자료의 신뢰도, 정확성 등에 대하여 책임지지 않습니다.</p>
<p>회사는 파트너 회원이 제공하는 정보, 상담 내용, 서비스 품질 및 이용자와 파트너 회원 간 거래 결과에 대하여 책임을 지지 않습니다. 대출상담 관련 정보는 참고용이며, 과도한 채무는 개인의 신용에 악영향을 줄 수 있습니다.</p>

<h2>제6조의2 (유료 서비스)</h2>
<p>회사는 파트너 회원을 대상으로 우선노출 등 유료 서비스를 제공할 수 있으며, 그 이용조건, 결제, 환불에 관한 사항은 별도로 정하는 바에 따릅니다.</p>

<h2>제7조 (분쟁의 해결)</h2>
<p>이 약관과 관련하여 회사와 이용자 간에 발생한 분쟁에 대하여는 대한민국 법을 준거법으로 하며, 분쟁으로 인한 소송은 관할 법원에 제기합니다.</p>

<h2>부칙</h2>
<p>이 약관은 2026년부터 시행합니다.</p>
<p>서비스 제공자: 빌드리머스 · 대표 조혜성</p>"""


_LEGAL_PRIVACY_SEED = """<h2>1. 개인정보의 처리 목적</h2>
<p>빌드리머스(이하 "회사")는 다음의 목적을 위하여 개인정보를 처리합니다. 처리한 개인정보는 다음의 목적 이외의 용도로는 이용되지 않으며, 이용 목적이 변경되는 경우에는 별도의 동의를 받는 등 필요한 조치를 이행합니다.</p>
<ul>
<li>회원 가입 및 관리</li>
<li>서비스 제공 및 문의 응대</li>
<li>관심 단지 알림 등 이용자 맞춤형 서비스 제공</li>
</ul>

<h2>2. 처리하는 개인정보 항목</h2>
<ul>
<li>필수항목: 이메일, 이름, 비밀번호(암호화하여 저장)</li>
<li>소셜 로그인 이용 시: 카카오 계정 식별자 및 프로필 정보</li>
<li>자동 수집 항목: 접속 IP, 쿠키, 서비스 이용 기록</li>
</ul>
<p>파트너 회원(중개사·운영지원업체·대출상담사) 가입 시</p>
<ul>
<li>필수항목: 대표자명, 연락처, 이메일, 사업자등록번호(또는 중개사무소 등록번호, 대출모집인 등록번호)</li>
<li>선택항목: 여권용 사진(중개사), 자격증·등록증 등 첨부서류</li>
</ul>

<h2>3. 개인정보의 처리 및 보유 기간</h2>
<p>회사는 법령에 따른 개인정보 보유·이용기간 또는 정보주체로부터 개인정보를 수집 시에 동의받은 보유·이용기간 내에서 개인정보를 처리·보유합니다.</p>
<ul>
<li>회원 정보: 회원 탈퇴 시까지 (부정이용 방지를 위해 탈퇴 후 최대 30일간 보관 후 파기)</li>
<li>파트너 신청 서류: 반려 시 즉시 파기, 승인 시 파트너 자격 유지 기간 동안 보관 후 파기</li>
<li>전자상거래 등에서의 소비자보호에 관한 법률에 따른 계약 또는 청약철회 등에 관한 기록: 5년</li>
<li>통신비밀보호법에 따른 로그인 기록: 3개월</li>
</ul>

<h2>4. 개인정보의 제3자 제공</h2>
<p>회사는 정보주체의 개인정보를 제1조에서 명시한 범위 내에서만 처리하며, 정보주체의 동의, 법률의 특별한 규정 등 개인정보 보호법에 해당하는 경우에만 개인정보를 제3자에게 제공합니다.</p>

<h2>4의2. 개인정보 처리업무의 위탁</h2>
<p>회사는 원활한 서비스 제공을 위하여 다음과 같이 개인정보 처리업무를 위탁하고 있습니다.</p>
<table>
<thead><tr><th>수탁업체</th><th>위탁업무 내용</th></tr></thead>
<tbody>
<tr><td>(주)알리고</td><td>SMS 발송</td></tr>
<tr><td>Resend</td><td>이메일 발송</td></tr>
<tr><td>카카오</td><td>소셜 로그인</td></tr>
<tr><td>Replit(Object Storage)</td><td>첨부서류 파일 저장</td></tr>
</tbody>
</table>
<p>회사는 위탁계약 체결 시 개인정보보호법 제26조에 따라 개인정보가 안전하게 관리될 수 있도록 필요한 사항을 규정하고 있습니다.</p>

<h2>5. 개인정보의 파기 절차 및 방법</h2>
<p>회사는 개인정보 보유기간의 경과, 처리목적 달성 등 개인정보가 불필요하게 되었을 때에는 지체 없이 해당 개인정보를 파기합니다. 전자적 파일 형태의 정보는 복구 불가능한 방법으로 삭제합니다.</p>

<h2>6. 정보주체의 권리·의무 및 행사 방법</h2>
<p>정보주체는 회사에 대해 언제든지 개인정보 열람·정정·삭제·처리정지 요구 등의 권리를 행사할 수 있습니다. 개인정보 열람·정정·삭제·처리정지 요구는 아래로 접수해주시기 바랍니다.</p>
<ul>
<li>접수처(이메일): costac74888@gmail.com</li>
</ul>

<h2>7. 개인정보의 안전성 확보 조치</h2>
<p>회사는 개인정보의 안전성 확보를 위해 비밀번호 암호화, 접근권한 관리, 접속기록의 보관 등 관리적·기술적 보호조치를 시행하고 있습니다.</p>

<h2>8. 개인정보 보호책임자</h2>
<ul>
<li>개인정보 보호책임자: 조혜성 (빌드리머스 대표)</li>
</ul>

<h2>부칙</h2>
<p>이 개인정보처리방침은 2026년부터 시행합니다.</p>"""


# 2026-07-21 개정 전(초판) 시드 원문의 md5 — 관리자 수정 없이 초판 그대로인 행만
# 새 개정판으로 자동 교체하기 위한 지문. (관리자가 admin.html에서 한 글자라도
# 수정했다면 md5가 달라져 자동 교체 대상에서 제외된다.)
_LEGAL_PREV_SEED_MD5 = {
    "terms": "000c485737128061a5568d218862fe41",
    "privacy": "2f411e7ef0bdce3d74acecf3de1ffe0f",
}


def _seed_legal_documents():
    """
    이용약관/개인정보처리방침 초기 본문을 시드한다.
    - doc_type 기준 ON CONFLICT DO NOTHING이라 이미 있으면 덮어쓰지 않는다(관리자 수정 내용 보존).
    - 단, 기존 행이 '이전 시드 원문 그대로'(관리자 무수정)인 경우에만
      새 개정판으로 자동 교체한다 (프로덕션 등 다른 환경에 개정 내용 전파용).
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.executemany("""
            INSERT INTO legal_documents (doc_type, content)
            VALUES (%s, %s)
            ON CONFLICT (doc_type) DO NOTHING
        """, [("terms", _LEGAL_TERMS_SEED), ("privacy", _LEGAL_PRIVACY_SEED)])
        inserted = cur.rowcount
        upgraded = 0
        for doc_type, new_content in (("terms", _LEGAL_TERMS_SEED), ("privacy", _LEGAL_PRIVACY_SEED)):
            prev_md5 = _LEGAL_PREV_SEED_MD5.get(doc_type)
            if not prev_md5:
                continue
            cur.execute("""
                UPDATE legal_documents
                SET content = %s, updated_at = NOW()
                WHERE doc_type = %s AND md5(content) = %s
            """, (new_content, doc_type, prev_md5))
            upgraded += cur.rowcount
        conn.commit()
        if inserted or upgraded:
            print(f"legal_documents 시드 완료 (신규 {inserted}건, 개정 자동교체 {upgraded}건)")
    finally:
        cur.close()
        conn.close()


_WEEKLY_FEATURE_TIP_SEEDS = [
    (
        1,
        "실거래가 무료조회",
        "로그인 없이 건물명만 입력하면 국토부 실거래가 바로 확인",
        "지금 바로 써보기 →",
        "/",
    ),
    (
        2,
        "관심단지 등록하면 실거래 알림이 와요",
        "매주 이메일로 자동 알림",
        "지금 바로 써보기 →",
        "/",
    ),
    (
        3,
        "데이터랩 숙박통계",
        "전국 생숙 건물수·호실수·신고율 한눈에",
        "지금 바로 써보기 →",
        "/?datalab=lodging",
    ),
    (
        4,
        "매물내놓기 제한공개",
        "영업 중인 사실 보호하며 조용히 매각 시작",
        "지금 바로 써보기 →",
        "/guide#disclosure-guide",
    ),
    (
        5,
        "방재고 관리",
        "객실별 상태·보증금·월세·채널·만기일 한 곳에서",
        "지금 바로 써보기 →",
        "/guide#business-guide",
    ),
    (
        6,
        "거래 체크리스트 14개 항목",
        "건물전체 매물 거래 전 필수 확인",
        "지금 바로 써보기 →",
        "/guide",
    ),
    (
        7,
        "보류 기능",
        "철회 없이 매물을 잠시 중단하는 방법",
        "지금 바로 써보기 →",
        "/mypage",
    ),
    (
        8,
        "영업신고현황",
        "시도별 생숙 신고율을 데이터랩에서 확인",
        "지금 바로 써보기 →",
        "/?datalab=consign",
    ),
]


def _seed_weekly_feature_tips():
    """초기 8회차 기능 팁만 채우고, 운영 중 수정된 회차는 그대로 둔다."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.executemany("""
            INSERT INTO weekly_feature_tips
                (episode, title, body, cta_label, cta_url)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (episode) DO NOTHING
        """, _WEEKLY_FEATURE_TIP_SEEDS)
        inserted = cur.rowcount
        conn.commit()
        if inserted:
            print(f"weekly_feature_tips 시드 완료 ({inserted}건)")
    finally:
        cur.close()
        conn.close()


def _normalize_umd_nm_spaces():
    """transactions·master_buildings 양쪽의 umd_nm에서 공백을 제거해 정규화한다.

    address_utils.normalize_umd_nm 과 동일한 규칙(공백 제거)을 DB 행에 직접 적용.
    멱등 — 이미 정규화된 행은 WHERE umd_nm LIKE '% %' 조건에 걸리지 않아 건드리지 않음.
    SCHEMA_VERSION 갱신 직전에 한 번만 실행되므로 신규 배포·운영 DB 모두 자동 적용된다.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE transactions SET umd_nm = REPLACE(umd_nm, ' ', '') WHERE umd_nm LIKE '% %'")
        tx_cnt = cur.rowcount
        cur.execute("UPDATE master_buildings SET umd_nm = REPLACE(umd_nm, ' ', '') WHERE umd_nm LIKE '% %'")
        mb_cnt = cur.rowcount
        conn.commit()
        if tx_cnt or mb_cnt:
            print(f"umd_nm 공백 정규화: transactions {tx_cnt}건, master_buildings {mb_cnt}건 수정")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    init_db()
    print("DB 초기화 완료 (PostgreSQL)")


class BackgroundConnectionUnavailable(PoolError):
    """사용자 요청용 연결을 남기기 위해 백그라운드 대여를 미룰 때 사용한다."""

def _release_background_slot(slot):
    if slot is None:
        return
    try:
        slot.release()
    except ValueError:
        # 방어적으로 이중 반환을 무시한다. 실제 연결 lease의 idempotency와 맞춘다.
        _logger.warning("백그라운드 DB 연결 슬롯 이중 반환을 무시합니다.")

def background_connection_limit():
    """현재 풀에서 통계 등 저우선순위 작업에 허용할 최대 동시 대여 수."""
    with _connection_pool_lock:
        if _background_connection_slots is not None:
            return _background_connection_slot_limit

    minconn = _pool_size_from_env("DB_POOL_MINCONN", _POOL_MIN_CONNECTIONS)
    maxconn = _pool_size_from_env("DB_POOL_MAXCONN", _POOL_MAX_CONNECTIONS)
    maxconn = max(minconn, maxconn)
    return min(
        _background_pool_size_from_env(),
        max(0, maxconn - _POOL_RESERVED_FOR_REQUESTS),
    )

@contextmanager
def background_connection_priority():
    """현재 스레드의 DB 대여를 비차단 백그라운드 우선순위로 표시한다."""
    previous = getattr(_connection_priority, "background", False)
    _connection_priority.background = True
    try:
        yield
    finally:
        _connection_priority.background = previous
