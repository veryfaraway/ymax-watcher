# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased] - v2.0
### Added
- 크롤링/파싱 이상 감지 시 텔레그램으로 경고(Warning) 알림을 발송하는 Health Check 시스템 도입.
- GitHub Actions 워크플로우에 Playwright 브라우저 설치 및 캐싱(Cache) 단계 추가.
- `config.json`에 `area` (지역) 설정 추가.

### Changed
- **[CRITICAL]** CGV Next.js SPA 리뉴얼 및 내부 API 인증 강화에 대응하여 크롤링 엔진을 `requests` + `BeautifulSoup`에서 **Playwright 헤드리스 브라우저** 기반으로 전면 교체.
- 파싱 전략 변경: 정적 `span.imax` 태그 검색에서, JS 렌더링 후의 DOM 트리를 탐색하여 `img[alt*="IMAX"]` 배지와 영화 제목(`[class*="title2"]` 등)을 연결짓는 동적 파싱으로 변경.
- 예매 페이지의 네비게이션 플로우 구현 (메인 접속 -> 팝업 닫기 -> 예매 진입 -> 서울 탭 -> 용산아이파크몰 선택 -> 날짜 탭 클릭 -> 파싱).

## [1.0.0] - 2026-07-15
### Added
- 초기 릴리스.
- CGV 용산아이파크몰 (0013) 특정 날짜의 IMAX 예매 오픈 감지 기능.
- `requests` + `BeautifulSoup` 기반 iframe HTML 크롤링.
- `status.json` 파일 기반 상태 관리로 중복 알림 방지.
- 예매 오픈 시 텔레그램(Telegram) 알림 발송.
- GitHub Actions를 통한 KST 08:00~23:00 정기 자동 실행.
- `DRY_RUN` 모드 지원 (알림 발송 생략 테스트 목적).
