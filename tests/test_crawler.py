import os
from pathlib import Path
from datetime import datetime, timedelta
import pytest

from watcher import (
    parse_imax_status,
    compare_and_detect,
    prune_past_dates,
    KST
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"

def read_fixture(filename: str) -> str:
    with open(FIXTURE_DIR / filename, "r", encoding="utf-8") as f:
        return f.read()

def test_parse_imax_opened():
    html = read_fixture("sample_imax_opened.html")
    imax_opened, movie_title = parse_imax_status(html)
    assert imax_opened is True
    assert movie_title == "인셉션 재개봉"

def test_parse_imax_closed():
    html = read_fixture("sample_imax_closed.html")
    imax_opened, movie_title = parse_imax_status(html)
    assert imax_opened is False
    assert movie_title == ""

def test_parse_malformed():
    html = read_fixture("sample_malformed.html")
    imax_opened, movie_title = parse_imax_status(html)
    assert imax_opened is False
    assert movie_title == ""

def test_compare_new_open():
    old_status = {
        "dates": {
            "20260722": {"imax_opened": False, "movie_title": ""}
        }
    }
    current_results = {
        "20260722": {"imax_opened": True, "movie_title": "인셉션 재개봉"}
    }
    
    alerts = compare_and_detect(old_status, current_results)
    
    assert len(alerts) == 1
    assert alerts[0]["date"] == "20260722"
    assert alerts[0]["movie_title"] == "인셉션 재개봉"

def test_compare_already_open():
    old_status = {
        "dates": {
            "20260722": {"imax_opened": True, "movie_title": "인셉션 재개봉"}
        }
    }
    current_results = {
        "20260722": {"imax_opened": True, "movie_title": "인셉션 재개봉"}
    }
    
    alerts = compare_and_detect(old_status, current_results)
    
    assert len(alerts) == 0

def test_prune_past_dates():
    today = datetime.now(KST).strftime("%Y%m%d")
    yesterday = (datetime.now(KST) - timedelta(days=1)).strftime("%Y%m%d")
    tomorrow = (datetime.now(KST) + timedelta(days=1)).strftime("%Y%m%d")
    
    status = {
        "dates": {
            yesterday: {"imax_opened": True, "movie_title": "A"},
            today: {"imax_opened": True, "movie_title": "B"},
            tomorrow: {"imax_opened": False, "movie_title": ""}
        }
    }
    
    new_status = prune_past_dates(status)
    
    assert yesterday not in new_status["dates"]
    assert today in new_status["dates"]
    assert tomorrow in new_status["dates"]
