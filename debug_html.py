"""Playwright로 CGV 예매 페이지에서 극장별 상영시간표 IMAX 감지 테스트"""
import asyncio
import json
from playwright.async_api import async_playwright

async def check_imax_schedule():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()
        
        # 1. CGV 접속 → 팝업 닫기 → 예매 페이지 진입
        await page.goto("https://www.cgv.co.kr/", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1000)
        try:
            await page.locator(".mmns00008_close__BeES6").first.click(force=True, timeout=2000)
        except:
            pass
        
        await page.locator("button:has-text('예매·예약')").first.click()
        await page.wait_for_timeout(5000)
        print(f"예매 페이지: {page.url}")
        
        # 2. "극장별 예매" 섹션에서 극장 선택 버튼 클릭
        content = await page.content()
        print(f"'극장별' 출현: {content.count('극장별')}")
        print(f"'극장을 선택' 출현: {content.count('극장을 선택')}")
        
        # "극장을 선택해 주세요" 버튼 클릭
        try:
            await page.locator("button:has-text('극장을 선택해 주세요')").first.click()
            await page.wait_for_timeout(3000)
            print("극장 선택 다이얼로그 열림!")
            
            # 다이얼로그 안의 UI 요소 확인
            dialog_elements = await page.evaluate("""() => {
                const dialog = document.querySelector('[role="dialog"], [class*="modal"], [class*="popup"], [class*="drawer"]');
                if (!dialog) return {found: false, elements: []};
                
                const els = Array.from(dialog.querySelectorAll('button, a, li, [role="option"]'))
                    .map(el => ({
                        tag: el.tagName,
                        text: (el.textContent || '').trim().substring(0, 50),
                        class: (el.className || '').toString().substring(0, 60),
                        visible: el.offsetParent !== null,
                    }))
                    .filter(e => e.text && e.visible)
                    .slice(0, 30);
                
                return {found: true, elements: els};
            }""")
            
            if dialog_elements.get('found'):
                print(f"\n  다이얼로그 내 요소 {len(dialog_elements['elements'])}개:")
                for el in dialog_elements['elements']:
                    print(f"    <{el['tag']}> '{el['text']}' class='{el['class'][:40]}'")
                
                # 서울 클릭
                try:
                    await page.locator("button:has-text('서울')").first.click()
                    await page.wait_for_timeout(2000)
                    print("\n  서울 선택 완료!")
                    
                    # 용산아이파크몰 클릭
                    try:
                        yongsan = page.locator("button:has-text('용산아이파크몰')")
                        if await yongsan.count() > 0:
                            await yongsan.first.click()
                            await page.wait_for_timeout(2000)
                            print("  용산아이파크몰 선택 완료!")
                        else:
                            # 리스트에서 찾기
                            yongsan_li = page.locator("text=용산아이파크몰")
                            if await yongsan_li.count() > 0:
                                await yongsan_li.first.click()
                                await page.wait_for_timeout(2000)
                                print("  용산아이파크몰 선택 (text)!")
                    except Exception as e:
                        print(f"  용산 선택 실패: {e}")
                except Exception as e:
                    print(f"  서울 선택 실패: {e}")
            else:
                print("  다이얼로그를 찾지 못함")
                
        except Exception as e:
            print(f"극장 선택 버튼 실패: {e}")
        
        # 3. 현재 상태에서 날짜 선택 확인
        await page.wait_for_timeout(2000)
        content2 = await page.content()
        print(f"\n극장 선택 후:")
        print(f"  IMAX 출현: {content2.count('IMAX')}")
        print(f"  '상영시간' 출현: {content2.count('상영시간')}")
        
        # 날짜 관련 버튼 찾기
        date_buttons = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('button'))
                .map(b => ({text: b.textContent?.trim()?.substring(0,30) || '', class: b.className?.substring(0,60) || ''}))
                .filter(b => b.text.match(/\\d{1,2}/) && b.text.length < 15)
                .slice(0, 30);
        }""")
        print(f"\n  날짜 버튼 후보 {len(date_buttons)}개:")
        for db in date_buttons[:15]:
            print(f"    '{db['text']}' class='{db['class'][:40]}'")
        
        # 영화/상영관 관련 정보
        movie_info = await page.evaluate("""() => {
            const results = [];
            // img[alt] 에서 IMAX 찾기
            document.querySelectorAll('img[alt*="IMAX"]').forEach(img => {
                let card = img.closest('li, [class*="item"], [class*="card"], [class*="movie"]');
                results.push({
                    type: 'img',
                    alt: img.alt,
                    cardText: card?.textContent?.trim()?.replace(/\\s+/g,' ')?.substring(0,200) || '',
                    cardHTML: card?.innerHTML?.substring(0,500) || '',
                });
            });
            // 영화 제목 후보
            document.querySelectorAll('[class*="movNm"], [class*="movie-name"], [class*="title"]').forEach(el => {
                const text = el.textContent?.trim();
                if (text && text.length > 1 && text.length < 50) {
                    results.push({type: 'title', text, class: el.className?.substring(0,60) || ''});
                }
            });
            return results.slice(0, 20);
        }""")
        
        print(f"\n  영화/IMAX 정보 {len(movie_info)}개:")
        for mi in movie_info:
            if mi.get('type') == 'img':
                print(f"    [IMAX IMG] alt='{mi['alt']}' cardText='{mi['cardText'][:80]}'")
            else:
                print(f"    [title] '{mi.get('text','')}' class='{mi.get('class','')[:40]}'")
        
        await browser.close()

asyncio.run(check_imax_schedule())
