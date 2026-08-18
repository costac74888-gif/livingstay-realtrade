# -*- coding: utf-8 -*-
"""
tests/test_prewarm_unit_areas.py — prewarm_unit_areas 배치 동작 단위 테스트

외부 DB·API 없이 mock으로 핵심 동작을 검증:
  1. API가 정상 응답하되 0건이면 sentinel(NULL) 저장 & consec_err 초기화
  2. 전송 오류(HTTP/XML 파싱 실패)면 sentinel 미저장 & consec_err 증가
  3. API가 HTTP 200을 반환해도 resultCode가 비-"00"이면 오류(sentinel 미저장)
  4. 연속 10건 오류 시 즉시 중단
  5. 정상 응답(>0건)이면 실제 (ho, sqm) 행 저장 & consec_err 초기화

실행: python tests/test_prewarm_unit_areas.py
"""

import os
import sys

# 프로젝트 루트를 경로에 추가 (api_test.py 등과 동일한 패턴)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from unittest.mock import MagicMock, patch, call

# ---------------------------------------------------------------------------
# 테스트 픽스처: DB·외부 의존성 모킹
# ---------------------------------------------------------------------------

class _FakeRow(dict):
    """psycopg2 RealDictRow 흉내 — dict처럼 접근 가능."""
    pass


def _make_building(bid=1, name="테스트건물", sgg_cd="11110", umd_nm="청운효자동", jibun="1"):
    return _FakeRow(id=bid, building_name=name, sgg_cd=sgg_cd, umd_nm=umd_nm, jibun=jibun)


class TestSaveAreas(unittest.TestCase):
    """_save_areas: 정상 rows / 빈 rows 저장 동작."""

    def setUp(self):
        import prewarm_unit_areas as pw
        self.pw = pw
        self.cur = MagicMock()

    def test_saves_rows_when_data_present(self):
        raw = [("101호", 33.0), ("102호", 49.5)]
        with patch("prewarm_unit_areas.execute_values") as mock_ev:
            self.pw._save_areas(self.cur, building_id=1, raw=raw)
            self.cur.execute.assert_called_once()  # DELETE only
            delete_sql = self.cur.execute.call_args[0][0]
            self.assertIn("DELETE", delete_sql)
            mock_ev.assert_called_once()  # execute_values로 실제 행 삽입

    def test_inserts_sentinel_when_empty(self):
        self.pw._save_areas(self.cur, building_id=2, raw=[])
        calls = self.cur.execute.call_args_list
        self.assertEqual(len(calls), 2)  # DELETE + sentinel INSERT
        sentinel_sql = calls[1][0][0]
        self.assertIn("INSERT", sentinel_sql)
        self.assertIn("NULL", sentinel_sql)


class TestRunBehavior(unittest.TestCase):
    """run(): sentinel/consec_err/daily_cap/skip 통합 동작."""

    def _make_run_env(self, buildings, fetch_side_effect):
        """
        run()을 직접 호출하지 않고 내부 루프 로직을 재현해
        fetch_expos_area_strict 교체·DB mock으로 검증한다.
        """
        import prewarm_unit_areas as pw

        conn = MagicMock()
        cur = MagicMock()
        cur.fetchall.return_value = buildings
        conn.cursor.return_value = cur

        bjdong = MagicMock()
        bjdong.find_bjdong_cd.return_value = "10100"

        saved_calls = []

        def fake_save(c, bid, raw):
            saved_calls.append((bid, list(raw)))

        with (
            patch.object(pw, "init_db"),
            patch.object(pw, "get_conn", return_value=conn),
            patch.object(pw, "BjdongMap", return_value=bjdong),
            patch.object(pw, "fetch_expos_area_strict", side_effect=fetch_side_effect),
            patch.object(pw, "_save_areas", side_effect=fake_save),
            patch.object(pw.time, "sleep"),
        ):
            result = pw.run(only_missing=True, sleep=0)

        return result, saved_calls

    def test_genuine_empty_writes_sentinel(self):
        """API가 정상 응답 0건 → sentinel 저장, n_empty 증가, n_err=0."""
        buildings = [_make_building(1)]
        result, saved = self._make_run_env(buildings, fetch_side_effect=[
            [],  # 정상 응답, 0건
        ])
        n_ok, n_empty, n_skip, n_err = result
        self.assertEqual(n_empty, 1)
        self.assertEqual(n_err, 0)
        self.assertEqual(saved, [(1, [])])

    def test_transport_error_no_sentinel(self):
        """HTTP/XML 오류 → sentinel 미저장, n_err 증가."""
        buildings = [_make_building(1)]
        result, saved = self._make_run_env(buildings, fetch_side_effect=[
            Exception("connection timeout"),
        ])
        n_ok, n_empty, n_skip, n_err = result
        self.assertEqual(n_err, 1)
        self.assertEqual(n_empty, 0)
        self.assertEqual(saved, [])  # sentinel 없음

    def test_consec_err_resets_after_success(self):
        """오류 후 성공하면 consec_err 초기화되어 10건 한도에 걸리지 않음."""
        buildings = [_make_building(i) for i in range(1, 6)]
        # ERR, OK, ERR, OK, OK 패턴
        effects = [
            Exception("err"),
            [("101호", 33.0)],
            Exception("err"),
            [("102호", 49.5)],
            [("103호", 66.0)],
        ]
        result, saved = self._make_run_env(buildings, fetch_side_effect=effects)
        n_ok, n_empty, n_skip, n_err = result
        self.assertEqual(n_ok, 3)
        self.assertEqual(n_err, 2)

    def test_consec_10_errors_stops_early(self):
        """연속 오류 10건 → 즉시 중단, 나머지 건물 미처리."""
        buildings = [_make_building(i) for i in range(1, 20)]  # 19건
        # 처음 10건 모두 오류
        effects = [Exception("quota")] * 10 + [[("1호", 33.0)]] * 9
        result, saved = self._make_run_env(buildings, fetch_side_effect=effects)
        n_ok, n_empty, n_skip, n_err = result
        self.assertEqual(n_err, 10)
        self.assertEqual(n_ok, 0)  # 중단 후 OK건 없음
        self.assertEqual(saved, [])

    def test_ok_rows_saved(self):
        """API가 전유부 반환 → 실제 행 저장, n_ok 증가."""
        buildings = [_make_building(1)]
        raw = [("101호", 33.05), ("102호", 49.50)]
        result, saved = self._make_run_env(buildings, fetch_side_effect=[raw])
        n_ok, n_empty, n_skip, n_err = result
        self.assertEqual(n_ok, 1)
        self.assertEqual(saved[0], (1, raw))

    def test_daily_cap_stops_loop(self):
        """OK+EMPTY가 daily_cap에 도달하면 나머지는 미처리."""
        import prewarm_unit_areas as pw

        buildings = [_make_building(i) for i in range(1, 6)]  # 5건
        effects = [[], [], [], [], []]  # 전부 empty

        conn = MagicMock()
        cur = MagicMock()
        cur.fetchall.return_value = buildings
        conn.cursor.return_value = cur
        bjdong = MagicMock()
        bjdong.find_bjdong_cd.return_value = "10100"

        processed = []

        def fake_save(c, bid, raw):
            processed.append(bid)

        with (
            patch.object(pw, "init_db"),
            patch.object(pw, "get_conn", return_value=conn),
            patch.object(pw, "BjdongMap", return_value=bjdong),
            patch.object(pw, "fetch_expos_area_strict", side_effect=effects),
            patch.object(pw, "_save_areas", side_effect=fake_save),
            patch.object(pw.time, "sleep"),
        ):
            result = pw.run(only_missing=True, sleep=0, daily_cap=3)

        n_ok, n_empty, n_skip, n_err = result
        self.assertLessEqual(n_ok + n_empty, 3)
        self.assertLessEqual(len(processed), 3)

    def test_successful_save_survives_later_error(self):
        """건물1 성공 후 건물2 API 오류 → 건물1 저장 내용이 rollback 없이 보존."""
        import prewarm_unit_areas as pw

        b1 = _make_building(1)
        b2 = _make_building(2)
        buildings = [b1, b2]

        committed = []  # conn.commit() 호출 시 저장된 bid 추적

        # 각 건물별 커밋 시점에 어떤 save가 이미 완료됐는지 기록
        saved_order = []

        conn = MagicMock()
        cur = MagicMock()
        cur.fetchall.return_value = buildings
        conn.cursor.return_value = cur

        def fake_commit():
            committed.append(list(saved_order))  # 커밋 시점 snapshot

        conn.commit.side_effect = fake_commit

        bjdong = MagicMock()
        bjdong.find_bjdong_cd.return_value = "10100"

        def fake_save(c, bid, raw):
            saved_order.append(bid)

        effects = [
            [("101호", 33.0)],      # 건물1: 성공
            Exception("API 장애"),   # 건물2: 실패
        ]

        with (
            patch.object(pw, "init_db"),
            patch.object(pw, "get_conn", return_value=conn),
            patch.object(pw, "BjdongMap", return_value=bjdong),
            patch.object(pw, "fetch_expos_area_strict", side_effect=effects),
            patch.object(pw, "_save_areas", side_effect=fake_save),
            patch.object(pw.time, "sleep"),
        ):
            result = pw.run(only_missing=True, sleep=0)

        n_ok, n_empty, n_skip, n_err = result
        self.assertEqual(n_ok, 1)
        self.assertEqual(n_err, 1)
        # 건물1 커밋은 건물2 오류 이전에 완료돼야 함
        self.assertGreaterEqual(len(committed), 1)
        self.assertIn(1, committed[0])  # 첫 커밋에 건물1 포함
        # 건물2 오류 시 rollback 호출 없음
        conn.rollback.assert_not_called()

    def test_skip_when_bjdong_not_found(self):
        """bjdong_cd 못 찾으면 sentinel 미저장, n_skip 증가."""
        import prewarm_unit_areas as pw

        buildings = [_make_building(1)]
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchall.return_value = buildings
        conn.cursor.return_value = cur
        bjdong = MagicMock()
        bjdong.find_bjdong_cd.return_value = None  # 못 찾음

        saved = []

        with (
            patch.object(pw, "init_db"),
            patch.object(pw, "get_conn", return_value=conn),
            patch.object(pw, "BjdongMap", return_value=bjdong),
            patch.object(pw, "_save_areas", side_effect=lambda *a, **k: saved.append(a)),
            patch.object(pw.time, "sleep"),
        ):
            result = pw.run(only_missing=True, sleep=0)

        n_ok, n_empty, n_skip, n_err = result
        self.assertEqual(n_skip, 1)
        self.assertEqual(saved, [])


class TestFetchExposAreaStrict(unittest.TestCase):
    """building_registry.fetch_expos_area_strict: 실패 시 예외, 성공 시 반환."""

    def test_raises_on_http_error(self):
        """HTTP 오류(raise_for_status) → 예외 전파."""
        import requests
        import building_registry as br

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("429")

        with patch.object(br, "_get_with_retry", return_value=mock_resp):
            with self.assertRaises(requests.HTTPError):
                br.fetch_expos_area_strict("11110", "10100", "0", "1", "0")

    def test_raises_on_xml_parse_error(self):
        """XML 파싱 오류 → 예외 전파."""
        import xml.etree.ElementTree as ET
        import building_registry as br

        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.content = b"<<INVALID XML"

        with patch.object(br, "_get_with_retry", return_value=mock_resp):
            with self.assertRaises(ET.ParseError):
                br.fetch_expos_area_strict("11110", "10100", "0", "1", "0")

    def test_returns_empty_list_on_zero_items(self):
        """정상 XML + 0건 → [] 반환(예외 없음)."""
        import building_registry as br

        xml_zero = b"""<?xml version="1.0" encoding="UTF-8"?>
<response><body><items></items><totalCount>0</totalCount></body></response>"""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.content = xml_zero

        with patch.object(br, "_get_with_retry", return_value=mock_resp):
            result = br.fetch_expos_area_strict("11110", "10100", "0", "1", "0")
        self.assertEqual(result, [])

    def test_raises_on_api_error_envelope_quota(self):
        """HTTP 200이지만 resultCode 99(쿼터 소진) → RuntimeError 전파."""
        import building_registry as br

        xml_err = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b"<response><header>"
            b"<resultCode>99</resultCode>"
            b"<resultMsg>LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR</resultMsg>"
            b"</header><body><items/><totalCount>0</totalCount></body></response>"
        )
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.content = xml_err

        with patch.object(br, "_get_with_retry", return_value=mock_resp):
            with self.assertRaises(RuntimeError) as ctx:
                br.fetch_expos_area_strict("11110", "10100", "0", "1", "0")
        self.assertIn("99", str(ctx.exception))

    def test_raises_on_api_error_envelope_auth(self):
        """HTTP 200이지만 resultCode 30(인증 실패) → RuntimeError 전파."""
        import building_registry as br

        xml_err = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b"<response><header>"
            b"<resultCode>30</resultCode>"
            b"<resultMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</resultMsg>"
            b"</header><body><items/><totalCount>0</totalCount></body></response>"
        )
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.content = xml_err

        with patch.object(br, "_get_with_retry", return_value=mock_resp):
            with self.assertRaises(RuntimeError) as ctx:
                br.fetch_expos_area_strict("11110", "10100", "0", "1", "0")
        self.assertIn("30", str(ctx.exception))

    def test_api_error_envelope_not_written_as_sentinel(self):
        """API 오류 envelope → prewarm에서 sentinel 미저장, n_err 증가."""
        import prewarm_unit_areas as pw
        import building_registry as br

        xml_err = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b"<response><header>"
            b"<resultCode>99</resultCode>"
            b"<resultMsg>LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR</resultMsg>"
            b"</header><body><items/><totalCount>0</totalCount></body></response>"
        )
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.content = xml_err

        buildings = [_make_building(1)]
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchall.return_value = buildings
        conn.cursor.return_value = cur
        bjdong = MagicMock()
        bjdong.find_bjdong_cd.return_value = "10100"

        saved = []

        with (
            patch.object(pw, "init_db"),
            patch.object(pw, "get_conn", return_value=conn),
            patch.object(pw, "BjdongMap", return_value=bjdong),
            patch.object(br, "_get_with_retry", return_value=mock_resp),
            patch.object(pw, "_save_areas", side_effect=lambda *a, **k: saved.append(a)),
            patch.object(pw.time, "sleep"),
        ):
            result = pw.run(only_missing=True, sleep=0)

        n_ok, n_empty, n_skip, n_err = result
        self.assertEqual(n_err, 1)
        self.assertEqual(saved, [])  # sentinel 없음

    def test_original_fetch_expos_area_swallows_errors(self):
        """(하위호환) fetch_expos_area는 예외를 삼켜 [] 반환."""
        import requests
        import building_registry as br

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500")

        with patch.object(br, "_get_with_retry", return_value=mock_resp):
            result = br.fetch_expos_area("11110", "10100", "0", "1", "0")
        self.assertEqual(result, [])

    def test_original_fetch_expos_area_swallows_api_envelope_error(self):
        """(하위호환) fetch_expos_area는 resultCode 오류도 삼켜 [] 반환."""
        import building_registry as br

        xml_err = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b"<response><header>"
            b"<resultCode>99</resultCode>"
            b"<resultMsg>QUOTA_EXCEEDED</resultMsg>"
            b"</header><body><items/><totalCount>0</totalCount></body></response>"
        )
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.content = xml_err

        with patch.object(br, "_get_with_retry", return_value=mock_resp):
            result = br.fetch_expos_area("11110", "10100", "0", "1", "0")
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
