# 🔍 알림 실패 원인 분석 보고서

> **분석일시**: 2026-07-19  
> **증상**: 7/31 IMAX 예매 오픈되었으나 텔레그램 알림 미수신  

---

## 🚨 근본 원인: CGV 사이트 전면 리뉴얼

CGV가 기존 ASP.NET 기반 사이트를 **Next.js SPA(Single Page Application)**로 전면 리뉴얼했습니다.

### 기존 (v1.0 설계 기반 — 작동 불가)
```
URL:  http://www.cgv.co.kr/common/showtimes/iframeTheater.aspx?theatercode=0013&date=YYYYMMDD
방식: 서버가 상영시간표 HTML을 직접 렌더링 → span.imax 태그 파싱
```

### 현재 (CGV 리뉴얼 후)
```
URL:  모든 URL이 Next.js SPA 쉘(약 87KB)로 응답 → 상영시간표 데이터 없음
방식: 브라우저가 JavaScript를 실행한 후 내부 API로 데이터를 동적 로드
변경: IMAX 표기가 텍스트(span.imax)에서 이미지(img[alt*="IMAX"])로 변경, 
      API는 401 인증을 요구하여 외부 직접 호출 불가
```

### 발견된 사실 타임라인

- 2026-07-15: v1.0 배포 및 테스트 완료 (HTML fetch는 200이었으나 IMAX가 없어 silent failure 상태였음)
- 2026-07-19: 7/31 예매 오픈되었으나 사용자 알림 미수신 제보 접수
- `status.json`이 7/15 이후 갱신 중단 확인
- 기존 iframe URL이 DOM 요소 `div.sect-showtimes`, `span.imax` 등을 전혀 렌더링하지 않음을 디버깅 스크립트를 통해 검증
- `/api/v1/booking/` 하위 내부 API 호출 시도 결과, 브라우저 세션/인증이 없으면 `401 Unauthorized` 반환 확인

---

## 📋 해결 조치 결과

**Playwright 헤드리스 브라우저를 통한 크롤링 엔진 재구축 완료 (v2.0)**

1. **크롤러 엔진 교체**: `requests` + `BeautifulSoup` 방식 폐기, `playwright` 기반 실제 브라우저 네비게이션 도입
2. **크롤링 플로우 재설계**: CGV 메인 ➡️ 예매 페이지 진입 ➡️ 서울 지역 ➡️ 용산아이파크몰 극장 ➡️ 해당 날짜 탭 클릭 ➡️ 상영 시간표 로딩 대기 ➡️ IMAX 탐색
3. **DOM 파싱 전략 재설정**: `img[alt*="IMAX"]` 및 `[class*="screenInfo_title"]` 조합의 복합 DOM 탐색 로직 적용
4. **Health Check (건강 체크) 도입**: 예매 버튼 실종, 극장/날짜 버튼 실종, 파싱 실패 등의 예외 상황을 감지하여 텔레그램 **경고 시스템** 구축 (향후 구조 변경 대응력 강화)
5. **GitHub Actions 업데이트**: Playwright Chromium 및 OS 의존성 설치 구문 추가 (실행 시간 단축을 위해 캐싱 적용)
