"""CGV booking API 기반으로 극장별 상영 스케줄 API를 탐색"""
import requests
import json

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
H = {"User-Agent": UA, "Referer": "https://www.cgv.co.kr/cnm/movieBook", "Accept": "application/json"}

# 발견된 API 패턴: /api/v1/booking/{function}
# searchAtktTopPostrList - 영화 리스트 (포스터)
# searchSscnsCdList - 특수관 코드
# searchOnlyCgvMovList - CGV 전용 영화 리스트
# 추측: searchPlaySchedule, searchScnsList, searchTheaterSchedule 등

booking_apis = [
    # 극장별 상영 스케줄 관련 추측
    ("GET", "/api/v1/booking/searchPlaySchedule", {"coCd": "A420", "siteNo": "0013", "playDe": "20260731"}),
    ("GET", "/api/v1/booking/searchScnsList", {"coCd": "A420", "siteNo": "0013", "playDe": "20260731"}),
    ("GET", "/api/v1/booking/searchTheaterSchedule", {"coCd": "A420", "siteNo": "0013", "playDe": "20260731"}),
    ("GET", "/api/v1/booking/searchMovieSchedule", {"coCd": "A420", "siteNo": "0013", "playDe": "20260731"}),
    ("GET", "/api/v1/booking/searchShowtime", {"coCd": "A420", "siteNo": "0013", "playDe": "20260731"}),
    ("GET", "/api/v1/booking/searchScheduleList", {"coCd": "A420", "siteNo": "0013", "playDe": "20260731"}),
    ("GET", "/api/v1/booking/searchAtktSchedule", {"coCd": "A420", "siteNo": "0013", "playDe": "20260731"}),
    ("GET", "/api/v1/booking/searchAtktScnsList", {"coCd": "A420", "siteNo": "0013", "playDe": "20260731"}),
    ("GET", "/api/v1/booking/searchAtktSiteScnsList", {"coCd": "A420", "siteNo": "0013", "playDe": "20260731"}),
    ("GET", "/api/v1/booking/searchScnsMovList", {"coCd": "A420", "siteNo": "0013", "playDe": "20260731"}),
    ("GET", "/api/v1/booking/searchSitePlayDe", {"coCd": "A420", "siteNo": "0013"}),
    ("GET", "/api/v1/booking/searchSitePlayDeList", {"coCd": "A420", "siteNo": "0013"}),
    ("GET", "/api/v1/booking/searchSiteMovList", {"coCd": "A420", "siteNo": "0013", "playDe": "20260731"}),
    ("GET", "/api/v1/booking/searchSiteScnsList", {"coCd": "A420", "siteNo": "0013", "playDe": "20260731"}),
    # POST 시도
    ("POST", "/api/v1/booking/searchPlaySchedule", {"coCd": "A420", "siteNo": "0013", "playDe": "20260731"}),
    ("POST", "/api/v1/booking/searchScnsList", {"coCd": "A420", "siteNo": "0013", "playDe": "20260731"}),
    ("POST", "/api/v1/booking/searchAtktScnsList", {"coCd": "A420", "siteNo": "0013", "playDe": "20260731"}),
    ("POST", "/api/v1/booking/searchSiteMovList", {"coCd": "A420", "siteNo": "0013", "playDe": "20260731"}),
    ("POST", "/api/v1/booking/searchSiteScnsList", {"coCd": "A420", "siteNo": "0013", "playDe": "20260731", "movNo": "30001192"}),
]

base = "https://cgv.co.kr"

for method, path, params in booking_apis:
    url = base + path
    try:
        if method == "GET":
            r = requests.get(url, params=params, headers=H, timeout=5)
        else:
            r = requests.post(url, json=params, headers={**H, "Content-Type": "application/json"}, timeout=5)
        
        is_spa = r.text.strip().startswith("<!DOCTYPE")
        status = r.status_code
        
        if is_spa:
            continue
            
        if status == 200:
            data = r.json()
            msg = data.get("statusMessage", "")
            has_data = data.get("data") is not None and data.get("data") != []
            marker = " ★★★ DATA!" if has_data else ""
            print(f"[{status}] {method} {path.replace('/api/v1/booking/','')} → {msg}{marker}")
            if has_data:
                print(f"  Response: {json.dumps(data, ensure_ascii=False)[:600]}")
                print()
        elif status == 404:
            data = r.json()
            real_path = data.get("statusMessage", "").replace("No endpoint ", "").replace(".", "")
            print(f"[404] {method} → real: {real_path}")
        elif status == 401:
            print(f"[401] {method} {path.replace('/api/v1/booking/','')} → 인증 필요")
        else:
            print(f"[{status}] {method} {path.replace('/api/v1/booking/','')} → {r.text[:100]}")
    except Exception as e:
        print(f"[ERR] {method} {path.replace('/api/v1/booking/','')} → {str(e)[:80]}")
