# 🛠 CGV 내부 예매 API 명세 및 디버깅 가이드

> **작성일**: 2026-07-19  
> **대상**: Next.js 기반으로 리뉴얼된 CGV 웹사이트 (2026년 7월 기준)  
> **목적**: 향후 AI 에이전트 또는 개발자가 CGV 상영시간표 시스템을 분석하고 디버깅하기 위한 레퍼런스 문서

---

## 1. 개요 및 한계점

CGV 사이트가 ASP.NET 기반에서 Next.js 기반의 동적 SPA(Single Page Application)로 전면 리뉴얼되면서, 상영시간표 등의 데이터는 모두 클라이언트 사이드 JavaScript가 실행된 후 내부 API 통신을 통해 로드됩니다.

⚠️ **중요 한계점 (API 인증)**
* 모든 `/api/v1/booking/...` 하위 예매 관련 엔드포인트는 **401 Unauthorized** 방어벽이 설정되어 있습니다.
* `requests`나 `curl` 등을 이용해 외부에서 쿠키 없이 단순 POST 요청을 보내면 접근이 거부됩니다.
* 인증 통과를 위해선 브라우저가 생성하는 세션 쿠키(`__cf_bm`, `_ga` 등)와 브라우저 컨텍스트가 필수적입니다.
* **따라서 API를 직접 추출하여 스크립트에서 활용하는 것은 극히 어렵고 (Cloudflare 봇 탐지 등), Playwright 등 실제 브라우저를 통한 데이터 파싱 기법이 권장됩니다.**

---

## 2. 주요 API 엔드포인트 목록

모든 API는 `POST` 방식을 사용하며, `Content-Type: application/json` 페이로드를 전달받습니다.

### 베이스 URL
`https://cgv.co.kr/api/v1/booking/`

### 핵심 엔드포인트 및 목적 (추정)

1. **`searchPlaySchedule`**
   * 상영 시간표 조회 (가장 핵심적인 데이터)
2. **`searchScnsList`** / **`searchAtktScnsList`**
   * 특정 극장/날짜에 대한 상영관(Screen) 목록 조회
3. **`searchSiteMovList`**
   * 특정 극장(`siteNo`) 및 날짜(`playDe`)에서 상영 중인 영화 목록 조회
4. **`searchSiteScnsList`**
   * 특정 극장(`siteNo`), 날짜(`playDe`), 영화(`movNo`)에 대한 상영관 상세 조회
5. **`searchMovPlayDeList`**
   * 특정 극장, 특정 영화에 대해 예매 가능한 날짜 목록 조회
6. **`searchSiteList`** / **`searchAtktSiteList`**
   * 예매 가능한 극장 목록 조회

---

## 3. Request Payload (JSON) 구조

각 API 엔드포인트 호출 시 공통적으로 사용되는 주요 파라미터 구조입니다.

```json
{
  "coCd": "A420",       // (필수) Company Code로 추정. CGV 한국 법인 코드
  "siteNo": "0013",     // 극장 코드 (예: 0013 = 용산아이파크몰)
  "playDe": "20260731", // 상영일자 (YYYYMMDD)
  "movNo": "30001192"   // (선택) 영화 식별자 (무비 차트 등에서 추출된 ID)
}
```

---

## 4. 디버깅 및 API 호출 전략 (AI Agent를 위한 가이드)

### 잘못된 접근 (HTTP Client 직접 호출)
```python
# 실패함: 401 Unauthorized 반환
import requests

url = "https://cgv.co.kr/api/v1/booking/searchSiteMovList"
payload = {"coCd": "A420", "siteNo": "0013", "playDe": "20260731"}
res = requests.post(url, json=payload)
```

### 올바른 디버깅 접근 (Playwright 브라우저 컨텍스트 인젝션)
만약 API 응답 데이터(JSON)를 분석해야만 하는 상황이라면, Playwright로 세션을 획득한 후 페이지 내에서 `fetch`를 발생시켜야 합니다.

```javascript
// Playwright page.evaluate() 내부에서 실행
const response = await fetch("https://cgv.co.kr/api/v1/booking/searchPlaySchedule", {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        coCd: "A420", 
        siteNo: "0013", 
        playDe: "20260731"
    }),
    credentials: 'include', // 인증 쿠키 포함 필수
});
const data = await response.json();
return data;
```

### 현재 시스템(v2.0)의 채택 방식
API 직접 분석 대신, 브라우저가 화면을 렌더링한 직후의 DOM 트리를 파싱하는 방식(End-to-End Test 방식)을 사용 중입니다. 
- 영화 제목 타겟팅: `[class*="title2"]`, `[class*="movNm"]`
- IMAX 상영관 타겟팅: `img[alt*="IMAX"]`
- DOM 파싱 전략은 `docs/analysis_20260719_cgv_renewal.md` 및 `watcher.py` 내 `_parse_schedule()` 함수 참고.
