# 🎬 Yong-IMAX Watcher (용아맥 예매 알리미)

> CGV 용산아이파크몰 IMAX관 예매가 열리면, 텔레그램으로 즉시 알려드립니다.

[![GitHub Actions](https://img.shields.io/badge/Powered%20by-GitHub%20Actions-2088FF?logo=github-actions&logoColor=white)](#)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](#)
[![Telegram](https://img.shields.io/badge/Alert-Telegram-26A5E4?logo=telegram&logoColor=white)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](#license)

---

## 왜 만들었나요?

CGV 용산아이파크몰 IMAX(일명 **용아맥**)는 국내 최고 사양의 IMAX 상영관으로, 대작 개봉 시 예매 경쟁이 치열합니다. 문제는 **예매 오픈 시점이 정해져 있지 않아** 수시로 CGV를 들여다봐야 한다는 것.

이 프로젝트는 GitHub Actions가 1시간마다 CGV를 확인하고, IMAX 예매가 열리는 순간 텔레그램으로 알림을 보내줍니다. **서버 비용 0원**.

---

## 주요 특징

| | 특징 | 설명 |
|---|---|---|
| 💰 | **Zero-Cost** | GitHub Actions 무료 티어만 사용, 별도 서버 불필요 |
| 🔔 | **즉시 알림** | 예매 오픈 감지 시 텔레그램으로 딥링크 포함 알림 |
| 🧠 | **중복 방지** | `status.json` 상태 관리로 동일 알림 1회만 발송 |
| ⏰ | **스마트 스케줄** | KST 08:00~23:00 사이에만 동작, 새벽 실행 제외 |
| 🛡️ | **장애 안전** | 재시도 로직, 파싱 실패 경고, 상태 유실 방지 |

---

## 동작 원리

```
┌─────────────┐     ┌───────────┐     ┌──────────┐     ┌──────────────┐
│ GitHub       │     │ CGV 웹    │     │ status   │     │ Telegram     │
│ Actions      │────▶│ 크롤링    │────▶│ 비교     │────▶│ 알림 발송    │
│ (1h 주기)    │     │ (IMAX)    │     │ (.json)  │     │ (오픈 시만)  │
└─────────────┘     └───────────┘     └──────────┘     └──────────────┘
                                           │
                                           ▼
                                    ┌──────────────┐
                                    │ Git Commit   │
                                    │ & Push       │
                                    └──────────────┘
```

1. **스케줄 실행** — GitHub Actions가 1시간 간격으로 `watcher.py`를 실행
2. **크롤링** — CGV 용산아이파크몰의 지정 날짜별 IMAX 상영 여부를 확인
3. **상태 비교** — 이전 `status.json`과 비교하여 새로 오픈된 날짜만 감지
4. **알림 발송** — 신규 오픈 건에 대해 텔레그램 메시지 발송
5. **상태 저장** — 최신 상태를 `status.json`에 커밋/푸시하여 다음 실행에 활용

---

## 빠른 시작

### 1. 리포지토리 Fork 또는 Clone

```bash
git clone https://github.com/{your-username}/ymax-watcher.git
cd ymax-watcher
```

### 2. 텔레그램 봇 설정

1. [@BotFather](https://t.me/BotFather)에서 봇 생성 → **Bot Token** 획득
2. 봇에게 메시지를 보낸 후, 아래 URL에서 **Chat ID** 확인:
   ```
   https://api.telegram.org/bot{YOUR_TOKEN}/getUpdates
   ```

### 3. GitHub Secrets 등록

리포지토리 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | BotFather에서 발급받은 토큰 |
| `TELEGRAM_CHAT_ID` | 알림 수신 채팅방 ID |

### 4. 감시 날짜 설정

[`config.json`](config.json)을 수정하여 감시할 날짜를 추가합니다:

```json
{
  "theater_code": "0013",
  "theater_name": "CGV 용산아이파크몰",
  "target_dates": ["20260722", "20260723", "20260724"]
}
```

### 5. 실행 확인

- **수동 실행**: Actions 탭 → `Yong-IMAX Watcher` → `Run workflow`
- **자동 실행**: 설정 완료 후 매시 정각에 자동으로 실행됩니다

---

## 프로젝트 구조

```
ymax-watcher/
├── .github/workflows/
│   └── run_watcher.yml      # GitHub Actions 워크플로우
├── docs/
│   ├── PRD_v1.0.md          # 제품 요구사항 정의서
│   └── implementation_plan.md # 작업 절차서
├── tests/
│   ├── test_crawler.py      # 유닛 테스트
│   └── fixtures/            # 테스트용 HTML 픽스처
├── config.json              # 감시 대상 설정
├── status.json              # 예매 상태 (자동 관리)
├── watcher.py               # 메인 로직
├── requirements.txt         # Python 의존성
└── README.md
```

---

## 알림 예시

```
🔔 용아맥 예매 오픈! 🔔

🎬 영화: 인셉션 재개봉
📅 상영일: 2026.07.22
🕐 감지 시각: 2026-07-15 18:00

👉 지금 바로 예매하세요!
https://m.cgv.co.kr/WebApp/MovieV4/movieDetail.aspx?theaterCd=0013&date=20260722
```

---

## 로컬 개발

```bash
# 의존성 설치
pip install -r requirements.txt

# Dry-run (텔레그램 발송 없이 테스트)
DRY_RUN=true python watcher.py

# 실제 실행 (환경변수 필요)
TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy python watcher.py

# 테스트
python -m pytest tests/ -v
```

---

## 스케줄링

| 항목 | 값 |
|---|---|
| Cron (UTC) | `0 23,0-14 * * *` |
| 동작 시간 (KST) | 08:00 ~ 23:00 |
| 실행 주기 | 매시 정각 (1시간 간격) |
| 일일 실행 횟수 | 16회 |
| 월간 예상 소비 | ~480분 (무료 2,000분 내) |

> **참고**: GitHub Actions의 cron 스케줄러는 시스템 부하에 따라 5~15분 지연될 수 있습니다.

---

## 제약사항

- CGV 공식 API가 아닌 **웹 크롤링** 기반이므로, CGV 사이트 구조 변경 시 파서 수정이 필요합니다.
- 예매 **자동 구매(티켓팅 봇)** 기능은 포함되어 있지 않으며, 범위 밖입니다.
- 현재 CGV 용산아이파크몰 IMAX관만 지원합니다.

---

## License

이 프로젝트는 [MIT License](LICENSE)를 따릅니다.
