# 홈앤스테이 건물·숙박시설 사진 호출 및 운영 매뉴얼

**문서 ID:** MAN-PHOTO-001  
**문서 버전:** V.01.0  
**기준일:** 2026-09-04  
**문서 상태:** 현행  
**다음 정기 검토일:** 2026-10-04  
**상위 정책:** `DATA_COLLECTION_GOVERNANCE_OPERATIONS_POLICY_V03_0_2026-09-04.md`  
**적용 범위:** 건물 상세 사진, 직접 업로드, TourAPI 숙박사진, Google Street View fallback, 관리자 사진 사전조회

---

## 1. 목적

이 매뉴얼은 건물 상세에서 사진이 어떤 순서로 선택되고, 사진이 없을 때 어떤 외부 공급자를 호출하며, 운영자가 언제 관리자 버튼을 눌러야 하는지를 정의한다.

핵심 목표:

1. 승인된 자체 사진을 외부 공급자 사진보다 우선한다.
2. TourAPI 숙박사진을 Street View보다 먼저 사용한다.
3. TourAPI에 적합한 사진이 없을 때만 Street View를 보조로 사용한다.
4. API 키가 포함된 URL이나 비공개 사진이 공개되지 않게 한다.
5. 외부 API 장애가 건물 상세 전체 장애로 번지지 않게 한다.
6. 같은 건물의 반복 호출을 캐시와 metadata 사전조회로 줄인다.

---

## 2. 사진 공급자 우선순위

사진은 낮은 우선순위 숫자가 먼저 선택된다.

| 순위 | 공급자/등록자 | 우선순위 값 | 용도 |
|---:|---|---:|---|
| 1 | 관리자 직접 등록 | 0 | 공식 대표사진 |
| 2 | 소유주·임대인·사업자 직접 등록 | 1 | 권한 확인된 현장사진 |
| 3 | 담당단지 중개사 등록 | 2 | 해당 건물과 직접 연결된 중개사 |
| 4 | 지역 담당 중개사 등록 | 3 | 지역 범위에서 승인된 중개사 |
| 5 | TourAPI | 9 | 관광공사 숙박 콘텐츠 대표사진 |
| 6 | Google Street View | 10 | TourAPI 사진이 없을 때 외관 보조 |
| 7 | VWorld | 11 | 기존 호환용 후순위 공급자 |

공개 사진 목록은 대표 우선순위, 등록 순서 등을 적용하고 최대 20장으로 제한한다.

### 2.1 금지

- Street View를 관리자·소유주·중개사 사진보다 앞에 표시
- TourAPI에 유효한 대표사진이 있는데 Street View를 기본사진으로 사용
- 외부 공급자 URL에 API 키를 붙여 DB나 공개 HTML에 저장
- 미승인 직접 업로드를 공개
- 제한공개 매물의 사진을 건물 공용사진으로 우회 공개

---

## 3. 사용자 건물 상세의 자동 호출 흐름

```text
건물 상세 열기
  → 기존 공개 가능 building_photos 조회
  → 직접 업로드/저장된 TourAPI 사진이 있으면 즉시 표시
  → 사진 metadata 상태 확인
  → TourAPI catalog 매칭 및 대표사진 유무 확인
  → TourAPI 사진이 있으면 저장 요청 후 다시 표시
  → TourAPI 최근 결과가 no_match 또는 catalog_no_photo이면
      Street View fallback 가능 여부 확인
  → Google quota·파노라마·품질검사 통과 시 Street View 표시
  → 모두 실패하면 사진 없음 상태 유지
```

### 3.1 최초 조회

공개 endpoint:

```text
GET /api/building/<BUILDING_ID>/photos
```

응답 역할:

- 기존 공개 가능 사진 반환
- TourAPI metadata 상태 반환
- 브라우저가 추가 fetch를 해야 하는지 `fetch_needed`로 안내
- 최근 no-match/no-photo 상태가 있으면 Street View 후보 상태 안내

브라우저 호출 함수:

```text
loadOnDemandBuildingPhotos(...)
```

### 3.2 TourAPI 사진 반영

브라우저가 허용된 TourAPI 이미지 URL을 확인한 뒤:

```text
POST /api/building/<BUILDING_ID>/photos/tourapi
```

서버는 다음을 검증한다.

- 허용된 TourAPI 호스트인지
- 해당 건물과 연결 가능한 metadata인지
- 중복 사진인지
- 공개 저장이 가능한 형식인지

결과 상태 예:

- `success`
- `catalog_matched`
- `catalog_no_photo`
- `no_match`
- `error`

### 3.3 Street View fallback

endpoint:

```text
GET /api/building-photo/<BUILDING_ID>/streetview?view=building-v6
```

Street View는 다음 조건을 모두 충족해야 한다.

1. TourAPI 우선 조회가 끝남
2. 최근 30일 이내 TourAPI 결과가 `no_match` 또는 `catalog_no_photo`
3. 건물 좌표가 있음
4. 월간 fallback 한도 이내
5. 공식 파노라마 metadata 호출 성공
6. 이미지 품질 거절 조건에 해당하지 않음

Street View는 DB의 영구 대표사진으로 취급하지 않고 요청 시 생성하는 보조 이미지다.

---

## 4. TourAPI 사전조회

### 4.1 관리자 버튼

관리자 사진 수집 영역:

```text
TourAPI 숙박 사진 유무 사전조회
```

실행 endpoint:

```text
POST /api/admin/prewarm-tourapi-metadata
```

상태 확인:

```text
GET /api/admin/sync-photos-status
```

### 4.2 버튼이 하는 일

- TourAPI `contentTypeId=32` 전국 숙박 목록을 페이지 단위로 조회
- 우리 건물을 한 건씩 TourAPI에서 검색하지 않음
- TourAPI 콘텐츠 주소와 건물 주소를 내부에서 매칭
- `contentId`, 매칭 여부, 대표사진 존재 여부를 metadata로 저장
- 공급자 키가 포함된 사진 URL은 공개 저장하지 않음

### 4.3 버튼을 눌러야 하는 경우

- TourAPI 원본이 갱신됐다고 판단될 때
- 신규 숙박 건물이 대량 추가된 뒤
- 관리자 상태에서 metadata가 오래됐을 때
- TourAPI 사진이 있어야 할 건물이 반복적으로 Street View로 내려갈 때
- 배포 후 사진 정책 또는 매칭 규칙이 변경됐을 때

### 4.4 버튼을 누르지 말아야 하는 경우

- 동일 사전조회가 실행 중일 때
- TourAPI 시크릿 또는 API 승인이 확인되지 않을 때
- 최근 실행이 정상 완료됐고 원본 변경 근거가 없을 때
- 외부 API 장애가 반복되며 retry 대기 상태일 때

### 4.5 정상 진행 표시

관리자 상태에서 확인할 값:

- 현재 상태
- 시작·종료 시각
- TourAPI 콘텐츠 처리 수
- 전체 페이지와 현재 페이지
- 주소 매칭 건물 수
- 대표사진 있음/없음
- provider retry 회차와 남은 대기시간
- 마지막 오류

첫 페이지 연결 중에는 전체 건물을 개별 조회하는 것처럼 보일 수 있으나, 실제로는 전국 catalog 목록을 가져오는 과정이다.

---

## 5. 캐시와 호출 제한

| 항목 | 정책 |
|---|---|
| TourAPI metadata 최신성 | 최근 30일 결과를 Street View 판단에 사용 |
| Street View HTTP 캐시 | 1일 |
| 브라우저 view cache key | `building-v6` |
| Street View 월간 fallback cap | 10,000건 |
| 과거 일괄 Street View 수집 | 사용 금지 |
| 직접 업로드 사진 | 삭제·승인 전까지 DB/Object Storage 유지 |
| TourAPI 저장 사진 | 공급자 검증과 중복검사 후 사용 |

월간 cap에 가까워지면 관리자 화면에서 사용량을 확인한다. 단순 재시도나 테스트도 실제 외부 호출이면 사용량에 포함될 수 있다.

---

## 6. 고층 건물 Street View 정책

최근접 파노라마가 항상 좋은 외관사진은 아니다. 고층 숙박시설은 건물 바로 앞 파노라마에서 저층 상가나 벽만 보일 수 있다.

고층 처리:

1. 최근접 파노라마 확인
2. 주변 4방향 공식 파노라마 추가 탐색
3. 건물 높이와 파노라마 거리 비교
4. 건물 중심을 향하는 heading 계산
5. 높이·거리 기반 pitch와 fov 계산
6. 품질 조건을 통과한 후보 선택

표시 규칙:

- 공급 이미지: 640×480
- 표시 비율: 4:3
- CSS: `contain`
- 위아래가 잘리지 않게 최대 높이 제한

브라우저 캐시 정책을 바꿀 때는 `building-v6` 같은 view 버전을 함께 변경해야 이전 잘못된 이미지가 남지 않는다.

---

## 7. 직접 업로드

### 7.1 권한

업로드 endpoint:

```text
POST /api/building/<BUILDING_ID>/photos/upload
```

허용:

- 관리자
- 해당 건물의 자격 있는 소유주·임대인·사업자
- 해당 건물 또는 지역의 승인된 중개사

### 7.2 파일 검증

- JPG 또는 PNG
- 최대 10MB
- 확장자뿐 아니라 실제 magic byte 검사
- 비관리자 업로드는 건물 위치·등록자 유형·중개사 인증 등 추가 검증
- SHA-256으로 중복 확인
- DB 저장 실패 시 Object Storage에 올린 파일을 정리

### 7.3 삭제

```text
DELETE /api/building/<BUILDING_ID>/photos/<PHOTO_ID>
```

- 관리자는 직접 업로드 사진을 관리할 수 있음
- 일반 등록자는 자신의 권한 범위 안에서만 삭제
- 매물 사진은 매물 편집 화면에서 삭제
- 외부 공급자 fallback 이미지를 직접 업로드처럼 삭제하지 않음

---

## 8. 자동과 수동 구분

| 작업 | 자동 | 수동 |
|---|---|---|
| 건물 상세의 기존 사진 조회 | 예 | - |
| TourAPI metadata 상태 확인 | 예 | - |
| 상세 진입 후 TourAPI lazy fetch | 예 | - |
| TourAPI 전국 metadata 사전조회 | 재시도·heartbeat만 자동 | 관리자 버튼으로 시작 |
| Street View fallback | 조건 충족 시 자동 | 개별 강제수집 금지 |
| 고층 파노라마 후보 선택 | 자동 | 샘플 품질 확인 |
| 관리자·소유주·중개사 업로드 | - | 사용자가 업로드 |
| 대표사진 우선순위 재계산 | 업로드/삭제 시 자동 | 이상 시 관리자 확인 |
| 사진 정책 변경 배포 | build/start 일부 자동 | 테스트·Publish·운영 확인 |

---

## 9. 사용하지 않는 경로

과거 endpoint:

```text
POST /api/admin/sync-photos?source=...
```

현재는 안전상 HTTP 409로 비활성화되어 있다.

운영자는 다음을 하지 않는다.

- Street View 전국 일괄 수집
- VWorld 전국 일괄 수집
- 비활성화 endpoint를 우회 호출
- `sync_building_photos.py`로 대량 외부사진을 임의 재수집

대량 사진 호출이 다시 필요하면 월간 비용·공급자 약관·공개 저장 방식·삭제 정책을 검토한 새 승인 절차를 먼저 만든다.

---

## 10. 장애별 점검

### 10.1 사진이 한 장도 안 보임

확인 순서:

1. `GET /api/building/<id>/photos` 응답
2. 기존 직접 업로드 존재 여부
3. TourAPI metadata 상태
4. 건물 주소·좌표
5. browser network 오류
6. Street View fallback 허용 상태
7. 외부 API 시크릿과 승인

### 10.2 TourAPI가 계속 재시도됨

- provider retry 회차와 대기시간 확인
- 첫 catalog 페이지 연결 장애인지 확인
- TourAPI 서비스 승인과 응답 코드 확인
- 실행 중 버튼을 반복 클릭하지 않음
- 재시도 한도 종료 후 원인을 수정하고 다시 실행

### 10.3 TourAPI에는 사진이 있는데 Street View가 표시됨

- metadata가 30일 이상 오래됐는지 확인
- catalog 주소가 건물 주소와 정확히 매칭되는지 확인
- `photo_available` 값 확인
- 허용 TourAPI 이미지 호스트인지 확인
- 브라우저의 이전 `building-v6` 캐시 확인

### 10.4 Street View가 건물을 향하지 않음

- 건물 좌표 정확성 확인
- 선택 파노라마 위치와 거리 확인
- heading·pitch·fov 확인
- 고층 후보 탐색이 실행됐는지 확인
- 같은 건물의 view cache version 확인

### 10.5 Street View가 빈 이미지 또는 저품질

- metadata API가 유효한 파노라마를 반환했는지 확인
- 품질 거절 사유 확인
- 최근접 후보만 강제 선택하지 않음
- TourAPI no-match/no-photo 선행 조건 확인
- 공급자 quota 초과 여부 확인

### 10.6 직접 업로드 실패

- 로그인과 등록자 권한
- 파일 크기·형식·magic byte
- 중복 해시
- Object Storage 상태
- DB insert 실패 후 orphan object가 정리됐는지 확인

---

## 11. 개인정보·보안

- 사진 URL에 API 키를 노출하지 않는다.
- 외부 공급자 키는 서버 secret으로만 사용한다.
- 제한공개 매물 사진은 권한 없는 사용자에게 제공하지 않는다.
- EXIF/GPS는 검증에 사용할 수 있지만 공개 응답은 최소화한다.
- 업로드 proxy는 DB의 공개 가능 기록과 권한을 확인한 뒤 파일을 제공한다.
- 오류 로그에 인증 쿼리 파라미터나 URL 인코딩된 키를 남기지 않는다.

---

## 12. 배포 전 검증

```bash
python -m unittest tests.building_photo_provider_test
python tests/smoke_test.py
python tests/api_test.py
```

확인 샘플:

- 직접 업로드가 있는 건물
- TourAPI 대표사진이 있는 건물
- TourAPI 주소 매칭은 되지만 사진이 없는 건물
- TourAPI 미매칭 건물
- 고층 건물
- 좌표가 없는 건물
- Street View 월간 cap 경계

---

## 13. 배포 후 운영 확인

- [ ] 관리자 사진 상태 API 정상
- [ ] TourAPI metadata 통계 표시
- [ ] Street View 월간 사용량 표시
- [ ] 직접 업로드 우선순위 유지
- [ ] TourAPI가 Street View보다 우선
- [ ] 고층 외관이 위아래 잘리지 않음
- [ ] 사진이 없는 건물에서 상세 전체가 깨지지 않음
- [ ] 공개 URL에 API 키가 없음
- [ ] browser console/network에 반복 오류가 없음

---

## 14. 운영자 빠른 판단표

| 증상 | 먼저 할 일 | 누르면 안 되는 것 |
|---|---|---|
| 여러 건물의 TourAPI 사진이 오래됨 | metadata 사전조회 상태 확인 후 버튼 실행 | Street View 전국 일괄수집 |
| 한 건물만 사진이 없음 | 해당 건물 photos API와 주소·좌표 확인 | 전국 prewarm 반복 |
| 고층 외관이 잘림 | view version·pitch·fov 확인 | 원본을 cover로 강제 |
| TourAPI 장애 | retry 상태와 공급자 응답 확인 | 실행 중 버튼 반복 클릭 |
| Street View cap 임박 | fallback 호출 원인 분석 | cap 임의 상향 |
| 직접 업로드 노출 오류 | 권한·공개 proxy·listing 공개범위 확인 | Object Storage URL 직접 공개 |

---

## 15. 버전 이력

| 버전 | 일자 | 변경 |
|---|---|---|
| V.01.0 | 2026-09-04 | 현행 사진 공급자 우선순위, TourAPI 사전조회, Street View fallback, 직접 업로드, 보안·장애복구 절차 최초 통합 |
