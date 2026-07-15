"""
Yong-IMAX Watcher — CGV 용산 IMAX 예매 오픈 감시 스크립트

Phase 1: 크롤링 엔진
Phase 2: 상태 관리 (TODO)
Phase 3: 텔레그램 알림 (TODO)
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
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
STATUS_PATH = BASE_DIR / "status.json"

CGV_SHOWTIMES_URL = (
    "http://www.cgv.co.kr/common/showtimes/iframeTheater.aspx"
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

HTTP_TIMEOUT = 15  # seconds
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds
REQUEST_DELAY_RANGE = (1.0, 2.0)  # seconds between requests

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
# Phase 1: Configuration
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

    return config


# ---------------------------------------------------------------------------
# Phase 1: Crawling Engine
# ---------------------------------------------------------------------------


def fetch_showtimes(theater_code: str, date: str) -> str | None:
    """
    CGV 상영시간표 iframe 페이지를 요청하여 HTML을 반환한다.

    Args:
        theater_code: CGV 극장 코드 (e.g., "0013")
        date: 조회 날짜 (YYYYMMDD 형식)

    Returns:
        HTML 문자열 또는 실패 시 None
    """
    params = {"theatercode": theater_code, "date": date}
    headers = {"User-Agent": USER_AGENT}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(
                CGV_SHOWTIMES_URL,
                params=params,
                headers=headers,
                timeout=HTTP_TIMEOUT,
            )
            response.raise_for_status()
            logger.info(
                "[%s] 크롤링 성공 (attempt %d, %d bytes)",
                date, attempt, len(response.text),
            )
            return response.text

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else "N/A"
            logger.warning(
                "[%s] HTTP 오류 %s (attempt %d/%d)",
                date, status_code, attempt, MAX_RETRIES,
            )
        except requests.exceptions.ConnectionError:
            logger.warning(
                "[%s] 연결 실패 (attempt %d/%d)",
                date, attempt, MAX_RETRIES,
            )
        except requests.exceptions.Timeout:
            logger.warning(
                "[%s] 요청 타임아웃 (attempt %d/%d)",
                date, attempt, MAX_RETRIES,
            )
        except requests.exceptions.RequestException as e:
            logger.warning(
                "[%s] 요청 오류: %s (attempt %d/%d)",
                date, e, attempt, MAX_RETRIES,
            )

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY)

    logger.error("[%s] %d회 시도 모두 실패. 스킵합니다.", date, MAX_RETRIES)
    return None


def parse_imax_status(html: str) -> tuple[bool, str]:
    """
    상영시간표 HTML에서 IMAX 상영 여부와 영화 제목을 파싱한다.

    CGV iframe 페이지 구조:
      div.sect-showtimes > ul > li  (영화별 컨테이너)
        div.info-movie > a > strong  (영화 제목)
        div.type-hall > div.info-hall > ul > li > a > span.imax  (IMAX 표기)

    Returns:
        (imax_opened, movie_title) 튜플.
        IMAX 상영이 없으면 (False, ""), 있으면 (True, "영화제목").
        복수 IMAX 영화가 있으면 첫 번째 영화를 반환한다.
    """
    soup = BeautifulSoup(html, "html.parser")

    # 영화별 컨테이너를 순회
    movie_items = soup.select("div.sect-showtimes > ul > li")

    for item in movie_items:
        # 해당 영화 블록 내에서 IMAX 상영관 존재 여부 확인
        imax_spans = item.select("span.imax")
        if not imax_spans:
            # "IMAX" 텍스트를 포함하는 span도 탐색 (클래스가 다를 수 있음)
            hall_names = item.select("div.info-hall span")
            imax_found = any("IMAX" in span.get_text() for span in hall_names)
            if not imax_found:
                continue

        # 영화 제목 추출
        title_tag = item.select_one("div.info-movie a strong")
        if title_tag:
            movie_title = title_tag.get_text(strip=True)
        else:
            # fallback: info-movie 내 텍스트
            info_movie = item.select_one("div.info-movie")
            movie_title = info_movie.get_text(strip=True) if info_movie else "제목 미상"

        logger.info("IMAX 상영 감지: %s", movie_title)
        return True, movie_title

    # IMAX 컨테이너를 못 찾은 경우 전체 HTML에서 한 번 더 확인
    if soup.find("span", class_="imax") or soup.find("span", string=lambda t: t and "IMAX" in t):
        logger.info("IMAX 태그 발견 (구조 불일치, 제목 미파싱)")
        return True, "제목 미상"

    return False, ""


def crawl_target_dates(config: dict) -> dict:
    """
    config의 target_dates를 순회하며 각 날짜의 IMAX 상영 상태를 크롤링한다.

    Args:
        config: load_config()로 읽은 설정 딕셔너리

    Returns:
        {
            "20260722": {"imax_opened": False, "movie_title": ""},
            "20260723": {"imax_opened": True, "movie_title": "인셉션 재개봉"},
        }
    """
    theater_code = config["theater_code"]
    target_dates = config["target_dates"]
    results = {}
    fetch_failures = 0

    for i, date in enumerate(target_dates):
        # 날짜 형식 검증
        if len(date) != 8 or not date.isdigit():
            logger.warning("잘못된 날짜 형식 스킵: %s (YYYYMMDD 필요)", date)
            continue

        html = fetch_showtimes(theater_code, date)

        if html is None:
            fetch_failures += 1
            # 크롤링 실패 시 이전 상태를 유지하기 위해 결과에 포함하지 않음
            continue

        imax_opened, movie_title = parse_imax_status(html)
        results[date] = {
            "imax_opened": imax_opened,
            "movie_title": movie_title,
        }

        logger.info(
            "[%s] IMAX=%s, 영화=%s",
            date,
            "오픈" if imax_opened else "미오픈",
            movie_title or "-",
        )

        # 다음 요청 전 랜덤 딜레이 (마지막 요청은 제외)
        if i < len(target_dates) - 1:
            delay = random.uniform(*REQUEST_DELAY_RANGE)
            time.sleep(delay)

    # 전체 크롤링 실패 시 경고 (HTML 구조 변경 의심)
    if target_dates and fetch_failures == len(target_dates):
        logger.error("모든 날짜의 크롤링이 실패했습니다. CGV 서버 상태를 확인하세요.")
    elif target_dates and len(results) > 0 and all(
        not r["imax_opened"] for r in results.values()
    ):
        # 정상 크롤링되었으나 모두 미오픈인 것은 정상 케이스
        logger.info("크롤링 완료: 모든 날짜 IMAX 미오픈 상태")

    return results


# ---------------------------------------------------------------------------
# Phase 2: State Management (TODO)
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
        if not result["imax_opened"]:
            continue

        old_entry = old_dates.get(date, {})
        was_opened = old_entry.get("imax_opened", False)

        if not was_opened:
            alerts.append({
                "date": date,
                "movie_title": result["movie_title"],
            })
            logger.info("🔔 신규 오픈 감지: %s — %s", date, result["movie_title"])

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
# Phase 3: Telegram Notification (TODO)
# ---------------------------------------------------------------------------


def is_dry_run() -> bool:
    """DRY_RUN 환경변수 확인."""
    return os.environ.get("DRY_RUN", "").lower() in ("true", "1", "yes")


def send_telegram_alert(movie_title: str, target_date: str) -> bool:
    """예매 오픈 알림을 텔레그램으로 발송한다."""
    # TODO: Phase 3에서 구현
    logger.info("[TODO] 텔레그램 알림 발송: %s (%s)", movie_title, target_date)
    return True


def send_telegram_warning(message: str) -> bool:
    """시스템 경고 알림을 텔레그램으로 발송한다."""
    # TODO: Phase 3에서 구현
    logger.info("[TODO] 텔레그램 경고 발송: %s", message)
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    logger.info("=" * 50)
    logger.info("Yong-IMAX Watcher 실행 시작")
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

    # 3. 크롤링 실행
    current_results = crawl_target_dates(config)

    if not current_results:
        logger.warning("크롤링 결과가 없습니다. 이전 상태를 유지합니다.")
        # TODO: Phase 3 — 전체 실패 시 경고 알림
        return

    # 4. 상태 비교 및 알림 대상 추출
    alerts = compare_and_detect(old_status, current_results)

    # 5. 알림 발송
    if is_dry_run():
        logger.info("[DRY_RUN] 알림 대상 %d건 (발송 생략)", len(alerts))
        for alert in alerts:
            logger.info("[DRY_RUN] → %s: %s", alert["date"], alert["movie_title"])
    else:
        for alert in alerts:
            send_telegram_alert(alert["movie_title"], alert["date"])

    # 6. 상태 업데이트 및 저장
    now = datetime.now(KST).isoformat()

    new_status = load_status()  # 최신 파일 기반으로 갱신
    new_status["last_checked"] = now

    for date, result in current_results.items():
        existing = new_status["dates"].get(date, {})
        new_status["dates"][date] = {
            "imax_opened": result["imax_opened"],
            "movie_title": result["movie_title"],
            "first_detected_at": existing.get("first_detected_at")
            or (now if result["imax_opened"] else None),
        }

    # 과거 날짜 정리
    new_status = prune_past_dates(new_status)

    save_status(new_status)

    # 7. 요약 로그
    opened_count = sum(
        1 for d in new_status["dates"].values() if d.get("imax_opened")
    )
    logger.info("-" * 50)
    logger.info(
        "실행 완료 | 크롤링: %d건 | 오픈: %d건 | 신규 알림: %d건",
        len(current_results),
        opened_count,
        len(alerts),
    )
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
