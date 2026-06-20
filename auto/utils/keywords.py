"""
실행마다 사용할 키워드를 자동 수집.
1순위: DataLab 트렌드 (당일 캐시 → 신규 수집 순)
2순위: 사용자 지정 키워드 풀 + 내장 풀 랜덤 선택
"""
import asyncio
import random
import json
import time
import urllib.parse
from datetime import date
from pathlib import Path

_CACHE_FILE = Path(__file__).parent.parent / "trend_cache.json"


def _load_trend_cache() -> list:
    try:
        if _CACHE_FILE.exists():
            data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
            if data.get("date") == str(date.today()):
                kws = data.get("keywords", [])
                if kws:
                    print(f"[키워드] 캐시 로드 ({data['date']}, {len(kws)}개) — DataLab 수집 생략")
                    return kws
    except Exception:
        pass
    return []


def _save_trend_cache(keywords: list) -> None:
    try:
        _CACHE_FILE.write_text(
            json.dumps({"date": str(date.today()), "keywords": keywords}, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception:
        pass

# ── 네이버 자동완성 시드 단어 ─────────────────────────────────────────────────
_SEEDS = [
    "오늘", "요즘", "맛집", "추천", "방법", "건강", "여행",
    "운동", "주식", "날씨", "가격", "후기", "레시피", "비교",
    "다이어트", "인테리어", "드라마", "영화", "핫플", "트렌드",
]

# ── 내장 키워드 풀 ────────────────────────────────────────────────────────────
_POOL = [
    # 날씨/계절
    "오늘 날씨", "주말 날씨", "미세먼지 오늘", "황사 예보", "자외선 지수",
    "봄 날씨", "여름 더위", "겨울 추위", "장마 예보", "태풍 경로",

    # 음식/맛집
    "맛집 추천", "혼밥 메뉴", "점심 메뉴 추천", "저녁 뭐먹을까", "배달 음식 추천",
    "간단한 요리 레시피", "에어프라이어 레시피", "다이어트 식단", "단백질 식품",
    "건강한 아침 식사", "편의점 신상", "카페 추천", "디저트 맛집",
    "한식 레시피", "파스타 만들기", "닭가슴살 요리", "샐러드 만들기",
    "국물 요리 레시피", "주말 브런치", "술안주 레시피",

    # 건강/운동
    "홈트 운동", "운동 루틴", "스트레칭 방법", "면역력 높이는 법",
    "수면 잘 자는 법", "눈 건강 관리", "허리 통증 완화", "목 스트레칭",
    "피로 회복 방법", "비타민 추천", "유산소 운동 효과", "근력 운동 입문",
    "걷기 운동 효과", "요가 초보", "필라테스 효과", "수영 배우기",
    "체중 감량 방법", "체지방 줄이기", "단백질 보충제 추천", "무릎 통증 원인",

    # 재테크/경제
    "주식 시황", "코스피 오늘", "금리 전망", "적금 추천", "예금 금리 비교",
    "ETF 투자 방법", "부동산 시장 전망", "청약 방법", "절세 방법",
    "연말정산 팁", "ISA 계좌 개설", "CMA 통장 추천", "달러 환율",
    "비트코인 시세", "금 시세 오늘", "배당주 추천", "월급 관리 방법",
    "재테크 입문", "소액 투자", "파이어족 준비",

    # 여행
    "국내여행 추천", "당일치기 여행", "서울 나들이", "제주도 여행 코스",
    "경주 여행", "강릉 여행", "부산 여행", "캠핑 명소", "글램핑 추천",
    "드라이브 코스", "야경 명소", "등산 코스 추천", "해수욕장 추천",
    "온천 여행", "해외여행 추천", "일본 여행", "동남아 여행",

    # IT/테크
    "스마트폰 비교", "갤럭시 vs 아이폰", "노트북 추천", "무선이어폰 비교",
    "태블릿 추천", "스마트워치 추천", "AI 활용법", "챗GPT 사용법",
    "유튜브 알고리즘", "앱 추천", "무선충전기 추천", "공유기 추천",
    "NAS 구축", "PC 업그레이드", "모니터 추천",

    # 문화/엔터
    "넷플릭스 추천", "요즘 드라마", "영화 추천 2025", "웹툰 추천",
    "책 추천", "자기계발 책", "소설 추천", "음악 플레이리스트",
    "유튜버 추천", "팟캐스트 추천", "전시회 추천", "뮤지컬 추천",

    # 뷰티/패션
    "스킨케어 루틴", "기초화장품 추천", "선크림 추천", "향수 추천",
    "봄 코디", "여름 코디", "남자 패션 추천", "여자 패션 추천",
    "헤어 스타일링", "네일 디자인", "다이어트 전후", "피부 트러블 원인",

    # 육아/반려동물
    "육아 꿀팁", "아이 간식 만들기", "어린이집 입소 준비",
    "강아지 산책 팁", "고양이 건강 관리", "반려동물 용품 추천",
    "강아지 훈련 방법", "고양이 사료 추천",

    # 생활/자기계발
    "집에서 할 수 있는 취미", "원데이클래스 추천", "그림 그리기 입문",
    "독서 습관 만들기", "시간 관리 방법", "아침 루틴", "영어 공부 방법",
    "자격증 추천", "부업 추천", "재택근무 팁", "정리정돈 방법",
    "미니멀라이프", "인테리어 DIY", "식물 키우기", "수경재배",
]


_DATALAB_JS = """() => {
    // 어제 날짜 문자열 계산 (예: "2026.06.19")
    const d = new Date();
    d.setDate(d.getDate() - 1);
    const ymd = d.getFullYear() + '.' +
        String(d.getMonth()+1).padStart(2,'0') + '.' +
        String(d.getDate()).padStart(2,'0');

    // 텍스트 노드를 순회하여 어제 날짜가 포함된 노드 탐색
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let dateNode = null, node;
    while ((node = walker.nextNode())) {
        if (node.textContent.trim().startsWith(ymd)) { dateNode = node; break; }
    }
    if (!dateNode) return [];

    // 날짜 노드에서 위로 올라가며 .rank_list 가진 컨테이너 탐색
    let el = dateNode.parentElement;
    for (let i = 0; i < 8; i++) {
        if (!el) break;
        const rl = el.querySelector('.rank_list');
        if (rl) {
            return [...rl.querySelectorAll('li')]
                .map(li => li.textContent.trim().replace(/^\\d+\\.?\\s*/, '').trim())
                .filter(t => t.length > 1 && /[가-힣]/.test(t))
                .slice(0, 10);
        }
        el = el.parentElement;
    }
    return [];
}"""

_CATEGORIES = [
    '패션의류', '패션잡화', '화장품/미용', '디지털/가전', '가구/인테리어',
    '출산/육아', '식품', '스포츠/레저', '생활/건강', '여가/생활편의', '면세점', '도서',
]


async def _fetch_datalab_trends(pw) -> list:
    """DataLab 분야별 인기 검색어 — 12카테고리 × 어제자 TOP10"""
    browser = None
    try:
        browser = await pw.chromium.launch(channel="chrome", headless=True)
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )
        page = await ctx.new_page()
        try:
            await page.goto("https://datalab.naver.com/", wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(1000)

            all_kws = await page.evaluate(_DATALAB_JS)

            for cat in _CATEGORIES[1:]:
                try:
                    await page.locator('a.select_btn').first.click()
                    await page.wait_for_timeout(150)
                    await page.locator(f'a.option:has-text("{cat}")').first.click()
                    await page.wait_for_timeout(700)
                    all_kws.extend(await page.evaluate(_DATALAB_JS))
                except Exception as e:
                    print(f"[키워드] {cat} 실패: {e}")

            result = list(dict.fromkeys(all_kws))
            _save_trend_cache(result)
            sample = random.sample(result, min(6, len(result)))
            print(f"[키워드] DataLab 트렌드 {len(result)}개 수집 (샘플: {sample})")
            return result

        finally:
            await page.close()
    except Exception as e:
        print(f"[키워드] DataLab 접근 실패: {type(e).__name__}: {e}")
        return []
    finally:
        if browser:
            await browser.close()


async def get_run_keywords(pw, cfg_keywords: list, count: int = 20) -> list:
    """
    실행마다 사용할 키워드 `count`개를 반환.
    - 당일 캐시 있으면 DataLab 수집 생략
    - DataLab 트렌드 수집 성공: 절반은 트렌드, 절반은 사용자/내장 풀에서 섞어서 반환
    - 수집 실패: 사용자/내장 풀에서만 랜덤 추출
    """
    trend_kws = _load_trend_cache() or await _fetch_datalab_trends(pw)

    fallback = list(cfg_keywords or []) + _POOL
    fallback = list(dict.fromkeys(k.strip() for k in fallback if k.strip()))

    if trend_kws:
        trend_kws = list(dict.fromkeys(k.strip() for k in trend_kws if k.strip()))
        trend_n = max(1, count // 2)
        fallback_n = count - trend_n
        random.shuffle(trend_kws)
        random.shuffle(fallback)
        pool = list(dict.fromkeys(trend_kws[:trend_n] + fallback[:fallback_n]))
        print(f"[키워드] 트렌드 {min(trend_n, len(trend_kws))}개 + 풀 {min(fallback_n, len(fallback))}개")
    else:
        pool = fallback
        print("[키워드] 트렌드 수집 실패 — 풀에서만 추출")

    random.shuffle(pool)
    return pool[:count]
