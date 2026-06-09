import json
import random
import urllib.request
import urllib.parse
import gemini_scraper

_SYSTEM_PROMPT = """당신은 네이버 블로그 전문 작가입니다.
주어진 키워드로 독자들이 실제로 유용하게 읽을 수 있는 블로그 글을 작성하세요.

글쓰기 규칙:
- 제목: SEO를 고려한 매력적인 한국어 제목 (50자 이하)
- 본문: 서론 → 본론(소제목 3~5개 포함) → 결론 구조, 2000자 내외
- 소제목은 ## 마크다운 형식 사용
- 친근하고 자연스러운 한국어 문체
- 불필요한 광고성 문구 없이 정보성 콘텐츠 위주

반드시 아래 JSON 형식으로만 응답하세요 (코드블록 없이 순수 JSON):
{
  "title": "블로그 제목",
  "content": "본문 내용 (마크다운 허용)",
  "image_prompt": "English prompt describing ONLY the blog topic subject. NEVER use: camera, DSLR, lens, photography"
}"""

_IMG_PROMPT_SYSTEM = """Convert a Korean keyword into a specific English image prompt.
- Output ONLY the prompt, no explanation
- Describe exactly what objects/food/people/places should be visible
- Example: '다이어트' → 'fresh salad bowl with colorful vegetables and grilled chicken on white plate'
- Example: '창원치과' → 'modern dental clinic interior with dental chair and medical equipment'
- NEVER use: camera, lens, DSLR, photography, photo, shot
- Max 25 words"""


def generate(keyword: str, extra_prompt: str = "", cancel_event=None) -> dict:
    full_prompt = f"{keyword}\n{extra_prompt}" if extra_prompt else keyword
    raw = gemini_scraper.query(full_prompt, cancel_event=cancel_event)
    return {"title": keyword, "content": raw.strip(), "image_prompt": ""}


def get_image_prompt(keyword: str) -> str:
    """키워드를 구글 번역으로 영어로 변환 후 FLUX용 프롬프트 생성 (~0.5초)"""
    try:
        url = ("https://translate.googleapis.com/translate_a/single"
               f"?client=gtx&sl=auto&tl=en&dt=t&q={urllib.parse.quote(keyword)}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
        translated = "".join(item[0] for item in result[0] if item[0]).strip()
    except Exception:
        translated = keyword

    quality_suffixes = [
        "photorealistic, sharp focus, natural lighting, professional photography, highly detailed",
        "cinematic lighting, dramatic composition, ultra high quality, 4K",
        "soft bokeh, professional camera, beautiful lighting, vivid colors",
        "documentary photography, authentic atmosphere, crystal clear detail",
        "vibrant colors, stunning composition, professional grade, HDR",
    ]
    return f"{translated}, {random.choice(quality_suffixes)}"
