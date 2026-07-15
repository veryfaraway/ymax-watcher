# [PRD] GitHub Actions 기반 용아맥(CGV 용산 IMAX) 예매 알리미

## 1. 개요 (Overview)

* **프로젝트명**: 용아맥 예매 개시 GitHub Actions 알리미 (Yong-IMAX Watcher)
* **목적**: CGV 용산아이파크몰 IMAX관의 예매 오픈 여부를 자동 감지하여, 예매가 열렸을 때 텔레그램으로 즉시 알림을 수신한다.
* **주요 특징**:
* **Zero-Cost Infrastructure**: 별도의 서버 구동 없이 GitHub Actions 무료 티어만 활용.
* **State Management**: 중복 알림 방지를 위해 마지막 예매 상태를 리포지토리에 JSON 파일로 커밋/푸시하여 상태를 저장.
* **Smart Schedule**: 불필요한 리소스 낭비 및 계정 제한을 피하기 위해 새벽 시간대를 제외한 주기적 배치 실행.



---

## 2. 사용자 시나리오 (User Scenario)

1. **사용자 환경 설정**: 사용자는 감지하고 싶은 영화 개봉 예정일(Target Dates) 리스트와 텔레그램 Bot 토큰 정보를 환경 변수(Secrets)에 등록한다.
2. **주기적 감시**: GitHub Actions가 스케줄러에 의해 지정된 주기(새벽 제외 1시간 간격)로 실행된다.
3. **상태 비교 및 탐지**:
* 스크립트가 CGV 서버에서 대상 날짜들의 상영시간표 데이터를 가져온다.
* "IMAX" 상영관 오픈 여부를 감지한다.
* 이전에 저장된 커밋 내역(JSON 상태 파일)과 비교하여 "새롭게 오픈된 상태"일 때만 텔레그램 알림을 발송한다.


4. **상태 업데이트 및 커밋**: 조회된 최신 상태 정보를 JSON 파일에 쓰고, GitHub Actions 봇이 이를 레포지토리에 자동으로 Commit & Push한다.

---

## 3. 기능 요구사항 (Functional Requirements)

### F-1. 예매 현황 크롤링 엔진

* CGV 용산아이파크몰(`theatercode=0013`)의 지정된 `target_dates` 리스트를 루프 돌며 크롤링한다.
* 일반 페이지가 아닌 시간표 실제 iframe 주소(`[http://www.cgv.co.kr/common/showtimes/iframeTheater.aspx](http://www.cgv.co.kr/common/showtimes/iframeTheater.aspx)`)를 타겟으로 동작한다.
* 응답 HTML에서 `span.imax` 태그의 존재 유무를 판별한다.

### F-2. 상태 저장 및 중복 알림 방지 (State Management)

* 크롤러는 매 실행 시마다 `status.json` 파일을 읽고 쓴다.
* **JSON 데이터 구조 예시**:
```json
{
  "last_checked": "2026-07-15T18:00:00Z",
  "dates": {
    "20260722": { "imax_opened": false, "movie_title": "" },
    "20260723": { "imax_opened": true, "movie_title": "인셉션 재개봉" }
  }
}

```


* **알림 발송 트리거 조건**:
* 이전 상태(`status.json` 내 특정 날짜)에서는 `imax_opened: false`였으나, 현재 크롤링 결과 `True`로 전환된 경우에만 알림을 보낸다. (이미 오픈되어 계속 True인 경우는 알림 제외)



### F-3. GitHub Actions 자동 커밋 및 푸시

* 크롤링 결과 생성되거나 업데이트된 `status.json` 파일을 Git Workflow 상에서 `git commit` 및 `git push`하여 원격 리포지토리에 업데이트한다.
* GitHub Actions 내에서 원격 푸시를 수행할 수 있도록 Workflow 권한(`contents: write`)을 부여한다.

### F-4. 텔레그램 알림 시스템

* 신규 오픈 감지 시, 구성된 텔레그램 API를 통해 포맷팅된 마크다운 메시지를 발송한다.
* **알림 메시지 템플릿**:
```text
🔔 [용아맥 예매 오픈!] 🔔

🎬 영화: {movie_title}
📅 상영일: {target_date}

지금 즉시 CGV 앱/웹으로 이동하세요!
👉 [CGV 예매 바로가기](https://m.cgv.co.kr)

```



---

## 4. 비기능 및 환경 요구사항 (Non-Functional Requirements)

### N-1. GHA 실행 스케줄링 (새벽 시간대 제외)

* GitHub Actions의 `cron` 스케줄러를 적용한다.
* **주의**: GitHub Action의 스케줄러는 **UTC 기준**으로 동작하므로 한국 표준시(KST = UTC+9)를 고려해 수식을 설계해야 한다.
* **동작 설계**: 한국 시간 기준 오전 8시 ~ 오후 11시 사이에만 1시간 주기로 실행되도록 설정한다.
* KST 08:00 ~ 23:00 $\rightarrow$ UTC 23:00 (전날) ~ 14:00 (당일)
* **Cron Expression**: `0 23,0-14 * * *` (매시 정각 실행)



### N-2. 보안 관리 (GitHub Secrets)

* 텔레그램 봇 토큰(`TELEGRAM_BOT_TOKEN`) 및 채팅방 ID(`TELEGRAM_CHAT_ID`)는 코드에 하드코딩하지 않고, GitHub Repository Secrets에 안전하게 저장하여 환경 변수로 주입한다.

### N-3. 안정성 및 Rate Limit 방지

* 로봇 탐지 우회를 위해 HTTP 요청 시 브라우저 헤더(`User-Agent`)를 필수로 모방한다.
* GitHub Actions 스케줄러는 시스템 상황에 따라 몇 분 정도 지연 실행될 수 있음을 감안하고 설계한다.

---

## 5. 시스템 아키텍처 및 폴더 구조 (Proposed Structure)

```text
yong-imax-watcher/
├── .github/
│   └── workflows/
│       └── run_watcher.yml   # GitHub Actions 워크플로우 정의 파일
├── status.json               # 예매 상태 저장 파일 (GHA가 수시로 커밋함)
├── watcher.py                # 크롤링, 상태 비교, 텔레그램 알림 전송 메인 로직
├── requirements.txt          # 필요 패키지 (requests, beautifulsoup4)
└── README.md

```

