"""
Yong-IMAX Watcher — CGV 용산 IMAX 예매 오픈 감시 스크립트

v2.0: Playwright 기반 크롤링 엔진 (CGV Next.js SPA 대응)
  - CGV가 Next.js SPA로 리뉴얼되면서 기존 requests+BeautifulSoup 파싱 불가
  - Playwright 헤드리스 브라우저로 예매 페이지 직접 탐색
  - 건강 체크(Health Check) 시스템으로 파싱 이상 감지 시 경고 알림

Phase 1: 크롤링 엔진 (Playwright)
Phase 2: 상태 관리
Phase 3: 텔레그램 알림 + 경고 알림
"""

import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

# .env 파일이 있다면 로드 (로컬 테스트용)
load_dotenv()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
STATUS_PATH = BASE_DIR / "status.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Playwright 설정
PW_TIMEOUT = 30000        # 30초
PW_NAV_WAIT = 5000        # 네비게이션 후 대기
PW_CLICK_WAIT = 2000      # 클릭 후 대기
PW_SCHEDULE_WAIT = 3000   # 상영시간표 로딩 대기

# 요청 간 딜레이 (Anti-ban)
REQUEST_DELAY_RANGE = (2.0, 5.0)

KST = timezone(timedelta(hours=9))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def load_config() -> dict:
    """config.json에서 극장 코드와 감시 대상 날짜 목록을 읽는다."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        logger.error("config.json 파일을 찾을 수 없습니다: %s", CONFIG_PATH)
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error("config.json 파싱 오류: %s", e)
        sys.exit(1)

    # 필수 필드 검증
    if "theater_code" not in config:
        logger.error("config.json에 'theater_code' 필드가 없습니다.")
        sys.exit(1)
    if "target_dates" not in config or not isinstance(config["target_dates"], list):
        logger.error("config.json에 'target_dates' 리스트가 없습니다.")
        sys.exit(1)
        
    if "hall_types" not in config:
        config["hall_types"] = ["IMAX"]  # 호환성을 위한 기본값

    return config


# ---------------------------------------------------------------------------
# Phase 1: Playwright 크롤링 엔진
# ---------------------------------------------------------------------------


def _close_popup(page) -> None:
    """CGV 메인 페이지 팝업 모달을 닫는다."""
    for selector in [".mmns00008_close__BeES6", "button:has-text('닫기')", "button:has-text('오늘은 그만 보기')"]:
        try:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=1500):
                btn.click(force=True)
                page.wait_for_timeout(500)
                logger.debug("팝업 닫기: %s", selector)
                return
        except Exception:
            continue


def _click_date_button(page, target_date: str) -> bool:
    """
    날짜 스크롤 바에서 목표 날짜 버튼을 클릭한다.

    CGV 날짜 버튼 형식:
      - 같은 달: "오늘19", "월20", ..., "금31"
      - 다음 달: "토8.1", "일02"

    Args:
        target_date: YYYYMMDD 형식
    Returns:
        클릭 성공 여부
    """
    target_day = int(target_date[6:8])
    target_month = int(target_date[4:6])
    today = datetime.now(KST)
    is_same_month = target_month == today.month

    # 날짜 버튼 목록을 가져온다
    day_buttons = page.locator("[class*='dayScroll_scrollItem']")
    count = day_buttons.count()

    if count == 0:
        logger.warning("날짜 스크롤바를 찾을 수 없습니다")
        return False

    for i in range(count):
        btn = day_buttons.nth(i)
        text = btn.text_content().strip()

        # 같은 달: "금31" → 끝의 숫자가 target_day와 일치
        # 다음 달: "8.1" → "M.D" 형식에서 M=target_month, D=target_day
        if is_same_month:
            # 텍스트에서 숫자 추출 (마지막 숫자들)
            import re
            match = re.search(r'(\d+)$', text)
            if match and int(match.group(1)) == target_day:
                btn.scroll_into_view_if_needed()
                btn.click()
                logger.info("[%s] 날짜 선택: '%s'", target_date, text)
                return True
        else:
            # "8.1" 형식
            target_str = f"{target_month}.{target_day}"
            # 또는 "02" (2자리 일)
            target_str2 = f"{target_day:02d}"
            if target_str in text or (not is_same_month and text.endswith(target_str2)):
                btn.scroll_into_view_if_needed()
                btn.click()
                logger.info("[%s] 날짜 선택: '%s'", target_date, text)
                return True

    logger.warning("[%s] 날짜 버튼을 찾지 못함 (버튼 %d개 검색)", target_date, count)
    return False


def _parse_schedule(page, hall_types: list[str]) -> list[dict]:
    """
    현재 렌더링된 예매 페이지에서 지정된 특수관 상영 여부를 파싱한다.
    DOM을 순회하며 영화 제목(title2 등)과 상영 타입의 연관성을 찾는다.

    Returns:
        [{"type": "SCREENX", "title": "영화이름"}, ...]
    """
    try:
        # 브라우저 컨텍스트 내에서 실행되는 DOM 분석 스크립트
        opened_movies = page.evaluate('''([types]) => {
            const results = [];
            
            // 전략 1: 영화 카드로 추정되는 블록(li, item, movie)에서 특수관 뱃지/텍스트와 제목을 함께 추출
            const movieCards = document.querySelectorAll('li, [class*="item"], [class*="movie"], [class*="card"], [class*="sect-showtimes"]');
            
            for (const card of movieCards) {
                const titleEl = card.querySelector('[class*="title2"], [class*="movNm"], [class*="movie-name"], strong');
                const title = titleEl ? titleEl.textContent.trim() : "";
                
                let foundType = null;
                for (const t of types) {
                    const hasImg = card.querySelector(`img[alt*="${t}"]`) !== null;
                    const hasText = card.textContent.toUpperCase().includes(t.toUpperCase());
                    if (hasImg || hasText) {
                        foundType = t;
                        break;
                    }
                }
                
                if (title && title.length > 1 && foundType) {
                    if (!results.some(r => r.title === title && r.type === foundType)) {
                        results.push({title: title, type: foundType});
                    }
                }
            }
            
            // 전략 2: 형제/이웃 요소 기반 탐색 (클래스 구조가 평탄화된 경우)
            if (results.length === 0) {
                const allTitles = document.querySelectorAll('[class*="screenInfo_title"]');
                for (let i = 0; i < allTitles.length; i++) {
                    const text = allTitles[i].textContent.trim();
                    let matchedType = types.find(t => text.toUpperCase().includes(t.toUpperCase()));
                    
                    if (matchedType) {
                        // 특수관 텍스트를 찾았으면 앞선 요소들 중 진짜 영화 제목을 찾음 (상영 타입 제외)
                        for (let j = i - 1; j >= 0; j--) {
                            const prevText = allTitles[j].textContent.trim();
                            const isScreenType = prevText.includes('2D') || prevText.includes('4DX') || 
                                                 prevText.includes('SCREENX') || prevText.includes('관') || prevText.includes('IMAX');
                            
                            if (prevText && !isScreenType && prevText.length > 1) {
                                if (!results.some(r => r.title === prevText && r.type === matchedType)) {
                                    results.push({title: prevText, type: matchedType});
                                }
                                break;
                            }
                        }
                    }
                }
            }
            
            return results;
        }''', [hall_types])
        
        if opened_movies:
            logger.info("특수관 감지: %s", ", ".join(f"{m['type']}({m['title']})" for m in opened_movies))
            return opened_movies
            
    except Exception as e:
        logger.error("상영시간표 파싱 스크립트 실행 중 오류: %s", e)
        
    return []


def crawl_target_dates(config: dict) -> tuple[dict, list[str]]:
    """
    Playwright로 CGV 예매 페이지에 접근하여 각 날짜의 IMAX 상영 상태를 확인한다.

    Args:
        config: load_config()로 읽은 설정 딕셔너리

    Returns:
        (results, health_issues) 튜플
        results: {"20260731": {"imax_opened": True, "movie_title": "스파이더맨"}, ...}
        health_issues: 건강 체크 이상 목록
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

    theater_name = config.get("theater_name", "용산아이파크몰").replace("CGV ", "")
    area = config.get("area", "서울")
    target_dates = config["target_dates"]
    results = {}
    health_issues = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        try:
            # ── Step 1: CGV 접속 ──
            logger.info("Playwright: CGV 접속 중...")
            page.goto("https://www.cgv.co.kr/", wait_until="networkidle", timeout=PW_TIMEOUT)
            page.wait_for_timeout(1000)
            _close_popup(page)
            logger.info("Playwright: CGV 메인 로드 완료")

            # ── Step 2: 예매 페이지 진입 ──
            booking_btn = page.locator("button:has-text('예매·예약')").first
            if not booking_btn.is_visible(timeout=5000):
                health_issues.append("'예매·예약' 버튼을 찾을 수 없습니다")
                raise RuntimeError("예매 버튼 미발견")

            booking_btn.click()
            page.wait_for_timeout(PW_NAV_WAIT)
            logger.info("Playwright: 예매 페이지 진입 → %s", page.url)

            if "/cnm/movieBook" not in page.url:
                health_issues.append(f"예매 페이지 URL 불일치: {page.url}")

            # ── Step 3: 극장 선택 ──
            theater_selector = page.locator("button:has-text('극장을 선택')")
            if theater_selector.count() == 0:
                health_issues.append("극장 선택 버튼을 찾을 수 없습니다")
                raise RuntimeError("극장 선택 버튼 미발견")

            theater_selector.first.click()
            page.wait_for_timeout(PW_CLICK_WAIT)

            # 지역 선택
            area_btn = page.locator(f"button:has-text('{area}')").first
            area_btn.click()
            page.wait_for_timeout(1000)

            # 극장 선택
            theater_btn = page.locator(f"button:has-text('{theater_name}')")
            if theater_btn.count() == 0:
                # fallback: 정확한 텍스트 매칭
                theater_btn = page.locator(f"text={theater_name}")

            if theater_btn.count() == 0:
                health_issues.append(f"극장 '{theater_name}'을 찾을 수 없습니다")
                raise RuntimeError(f"극장 미발견: {theater_name}")

            theater_btn.first.click()
            page.wait_for_timeout(PW_SCHEDULE_WAIT)
            logger.info("Playwright: 극장 '%s' 선택 완료", theater_name)

            # ── Health Check: 날짜 스크롤바 존재 확인 ──
            day_buttons = page.locator("[class*='dayScroll_scrollItem']")
            if day_buttons.count() == 0:
                health_issues.append("날짜 선택 스크롤바가 렌더링되지 않았습니다")

            # ── Health Check: 영화 목록 존재 확인 ──
            screen_info = page.locator("[class*='screenInfo_title']")
            if screen_info.count() == 0:
                health_issues.append("상영 정보(screenInfo)가 렌더링되지 않았습니다")

            # ── Step 4: 각 날짜별 IMAX 확인 ──
            for i, date_str in enumerate(target_dates):
                if len(date_str) != 8 or not date_str.isdigit():
                    logger.warning("잘못된 날짜 형식 스킵: %s", date_str)
                    continue

                try:
                    if not _click_date_button(page, date_str):
                        health_issues.append(f"[{date_str}] 날짜 버튼 클릭 실패")
                        continue

                    page.wait_for_timeout(PW_SCHEDULE_WAIT)

                    opened_movies = _parse_schedule(page, config["hall_types"])
                    results[date_str] = {
                        "opened_movies": opened_movies
                    }

                    if opened_movies:
                        for m in opened_movies:
                            logger.info("[%s] %s 오픈: %s", date_str, m['type'], m['title'])
                    else:
                        logger.info("[%s] %s 미오픈", date_str, "/".join(config["hall_types"]))

                except PwTimeout:
                    logger.error("[%s] 타임아웃 발생", date_str)
                    health_issues.append(f"[{date_str}] Playwright 타임아웃")
                except Exception as e:
                    logger.error("[%s] 파싱 오류: %s", date_str, e)
                    health_issues.append(f"[{date_str}] 파싱 오류: {e}")

                # Anti-ban 딜레이
                if i < len(target_dates) - 1:
                    delay = random.uniform(*REQUEST_DELAY_RANGE)
                    time.sleep(delay)

        except RuntimeError as e:
            logger.error("크롤링 중단: %s", e)
        except PwTimeout as e:
            logger.error("Playwright 전역 타임아웃: %s", e)
            health_issues.append(f"Playwright 전역 타임아웃: {e}")
        except Exception as e:
            logger.error("예기치 않은 오류: %s", e)
            health_issues.append(f"예기치 않은 오류: {e}")
        finally:
            browser.close()
            logger.info("Playwright: 브라우저 종료")

    return results, health_issues


# ---------------------------------------------------------------------------
# Phase 2: State Management
# ---------------------------------------------------------------------------


def load_status() -> dict:
    """status.json을 읽어 이전 상태를 반환한다."""
    try:
        with open(STATUS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"last_checked": None, "dates": {}}


def save_status(status: dict) -> None:
    """status.json에 현재 상태를 저장한다."""
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)
    logger.info("status.json 저장 완료")


def compare_and_detect(old_status: dict, current_results: dict) -> list[dict]:
    """
    이전 상태와 현재 크롤링 결과를 비교하여 신규 오픈된 항목을 반환한다.

    알림 트리거 조건: 이전 imax_opened=false → 현재 imax_opened=true

    Returns:
        [{"date": "20260722", "movie_title": "인셉션 재개봉"}, ...]
    """
    alerts = []
    old_dates = old_status.get("dates", {})

    for date, result in current_results.items():
        opened_movies = result.get("opened_movies", [])
        old_entry = old_dates.get(date, {})
        old_opened_movies = old_entry.get("opened_movies", [])
        
        # 이전엔 안 열렸는데 새로 열린 특수관/영화 조합 찾기
        for current in opened_movies:
            is_new = True
            for old in old_opened_movies:
                if old.get("title") == current["title"] and old.get("type") == current["type"]:
                    is_new = False
                    break
            
            # (호환성) 이전에 imax_opened가 true였고 현재 타입이 IMAX라면 새로 알림 안 줌
            if current["type"] == "IMAX" and old_entry.get("imax_opened") is True and old_entry.get("movie_title") == current["title"]:
                is_new = False
                    
            if is_new:
                alerts.append({
                    "date": date,
                    "movie_title": current["title"],
                    "hall_type": current["type"]
                })
                logger.info("🔔 신규 %s 오픈 감지: %s — %s", current["type"], date, current["title"])

    return alerts


def prune_past_dates(status: dict) -> dict:
    """현재 날짜 기준으로 이미 지난 날짜의 항목을 status에서 제거한다."""
    today = datetime.now(KST).strftime("%Y%m%d")
    dates = status.get("dates", {})
    past_dates = [d for d in dates if d < today]

    for d in past_dates:
        del dates[d]
        logger.info("과거 날짜 정리: %s", d)

    return status


# ---------------------------------------------------------------------------
# Phase 3: Telegram Notification
# ---------------------------------------------------------------------------


def is_dry_run() -> bool:
    """DRY_RUN 환경변수 확인."""
    return os.environ.get("DRY_RUN", "").lower() in ("true", "1", "yes")


def send_telegram_message(text: str) -> bool:
    """텔레그램 API를 호출하여 메시지를 발송한다."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        logger.error("텔레그램 환경변수(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)가 설정되지 않았습니다.")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }

    for attempt in range(1, 3):  # 최대 2회 재시도
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.warning("텔레그램 메시지 발송 실패 (attempt %d/2): %s", attempt, e)
            if attempt < 2:
                time.sleep(2)

    logger.error("텔레그램 메시지 발송을 최종 실패했습니다.")
    return False


def send_telegram_alert(movie_title: str, target_date: str, hall_type: str) -> bool:
    """예매 오픈 알림을 텔레그램으로 발송한다."""
    formatted_date = f"{target_date[:4]}.{target_date[4:6]}.{target_date[6:]}"
    detected_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    text = (
        f"🔔 *CGV {hall_type} 예매 오픈!* 🔔\n\n"
        f"🎬 영화: {movie_title}\n"
        f"📅 상영일: {formatted_date}\n"
        f"🕐 감지 시각: {detected_at}\n\n"
        f"👉 지금 바로 예매하세요!\n"
        f"https://www.cgv.co.kr/cnm/movieBook"
    )

    logger.info("텔레그램 알림 발송 시도: [%s] %s (%s)", hall_type, movie_title, target_date)
    return send_telegram_message(text)


def send_telegram_warning(message: str) -> bool:
    """시스템 경고 알림을 텔레그램으로 발송한다."""
    text = f"⚠️ *Yong-IMAX Watcher 경고* ⚠️\n\n{message}"
    logger.info("텔레그램 경고 발송 시도")
    return send_telegram_message(text)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    logger.info("=" * 50)
    logger.info("Yong-IMAX Watcher v2.0 실행 시작 (Playwright)")
    logger.info("=" * 50)

    # 1. 설정 로드
    config = load_config()
    target_dates = config["target_dates"]

    if not target_dates:
        logger.warning("감시 대상 날짜가 없습니다. config.json의 target_dates를 설정하세요.")
        return

    logger.info(
        "극장: %s (%s), 감시 날짜: %s",
        config.get("theater_name", ""),
        config["theater_code"],
        ", ".join(target_dates),
    )

    # 2. 이전 상태 로드
    old_status = load_status()

    # 3. Playwright 크롤링 실행
    current_results, health_issues = crawl_target_dates(config)

    # 4. 건강 체크 경고 발송
    if health_issues:
        warning_msg = "크롤링 중 이상이 감지되었습니다:\n\n"
        for issue in health_issues:
            warning_msg += f"• {issue}\n"
            logger.warning("Health Check: %s", issue)
        warning_msg += "\nCGV 사이트 구조 변경 등을 확인하세요."

        if not is_dry_run():
            send_telegram_warning(warning_msg)
        else:
            logger.info("[DRY_RUN] 경고 알림 발송 생략")

    if not current_results:
        logger.warning("크롤링 결과가 없습니다. 이전 상태를 유지합니다.")
        return

    # 5. 상태 비교 및 알림 대상 추출
    alerts = compare_and_detect(old_status, current_results)

    # 6. 알림 발송
    if is_dry_run():
        logger.info("[DRY_RUN] 알림 대상 %d건 (발송 생략)", len(alerts))
        for alert in alerts:
            logger.info("[DRY_RUN] → %s: [%s] %s", alert["date"], alert["hall_type"], alert["movie_title"])
    else:
        for alert in alerts:
            send_telegram_alert(alert["movie_title"], alert["date"], alert["hall_type"])

    # 7. 상태 업데이트 및 저장
    now = datetime.now(KST).isoformat()

    new_status = load_status()  # 최신 파일 기반으로 갱신
    new_status["last_checked"] = now

    for date, result in current_results.items():
        new_status["dates"][date] = {
            "opened_movies": result["opened_movies"]
        }

    # 과거 날짜 정리
    new_status = prune_past_dates(new_status)

    save_status(new_status)

    # 8. 요약 로그
    opened_count = sum(
        len(d.get("opened_movies", [])) for d in new_status["dates"].values()
    )
    logger.info("-" * 50)
    logger.info(
        "실행 완료 | 크롤링: %d건 | 오픈: %d건 | 신규 알림: %d건 | 경고: %d건",
        len(current_results),
        opened_count,
        len(alerts),
        len(health_issues),
    )
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
