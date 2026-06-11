"""
네이버 인기글 텍스트 수집
- 키워드로 인기글 상위 N개 URL 조회 (blog-ranking과 동일한 API)
- 각 포스팅 모바일 URL에서 본문 텍스트만 추출 (UI 노이즈 제거)
"""
import json
import re
import urllib.request
import urllib.parse

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://search.naver.com/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

_BLOG_PAT = re.compile(r'blog\.naver\.com/([A-Za-z0-9_.-]+)/(\d+)')

# Naver 블로그 모바일 페이지 UI 노이즈 필터
_NOISE_EXACT = {
    "게시판", "이웃추가", "본문 기타 기능", "본문 폰트 크기 조정",
    "본문 폰트 크기 작게 보기", "본문 폰트 크기 크게 보기",
    "가", "공유하기", "URL복사", "신고하기",
    "Previous image", "Next image", "blog.naver.com",
    "나", "다", "라", "마",
}
_NOISE_PREFIX = ("http://", "https://", "blog.naver", "m.blog.naver")
_NOISE_RE = re.compile(r'^\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.')  # 날짜 패턴


def _get(url: str, params: dict = None, timeout: int = 10) -> str:
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        charset = r.headers.get_content_charset() or "utf-8"
        return r.read().decode(charset, errors="replace")


def _strip_tags(html: str) -> str:
    html = re.sub(r'<(script|style|noscript)[^>]*>.*?</(script|style|noscript)>',
                  '', html, flags=re.DOTALL | re.I)
    text = re.sub(r'<[^>]+>', ' ', html)
    text = (text
            .replace('&quot;', '"').replace('&#34;', '"')
            .replace('&#39;', "'").replace('&apos;', "'")
            .replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&'))
    return re.sub(r'\s+', ' ', text).strip()


def _is_noise(line: str) -> bool:
    s = line.strip()
    if not s or len(s) < 2:
        return True
    if s in _NOISE_EXACT:
        return True
    if s.startswith(_NOISE_PREFIX):
        return True
    if s.startswith('#'):  # 해시태그 라인
        return True
    if _NOISE_RE.match(s):
        return True
    return False


def _fix_leading_punct(s: str) -> str:
    """선행 구두점+공백 아티팩트만 제거. 문장 끝 .!? 는 보존."""
    # '. 내용' 또는 '! 내용' 처럼 단독 구두점이 맨 앞에 붙은 경우만 제거
    return re.sub(r'^[.!?]\s+', '', s.strip()).strip()


def _split_sentences(text: str, delimiters=None) -> list:
    """문장 분리. delimiters 지정 시 해당 단어 + 후속 .!? 기준, 없으면 .!? 기준."""
    text = text.replace('\n', ' ')
    if delimiters:
        escaped = [re.escape(d) for d in delimiters if d.strip()]
        if escaped:
            # 단어에 붙지 않은 부유 마침표 전체 제거
            # '한국어단어.' 는 단어문자가 앞에 있으므로 보존, '. 문장' / '문장 . 다음' / '."문장' 은 제거
            text = re.sub(r'(?<!\w)\.\s*', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            pattern = '(' + '|'.join(escaped) + r'\s*[.!?]*)'
            parts = re.split(pattern, text)
            sentences = []
            i = 0
            while i < len(parts):
                if i + 1 < len(parts):
                    # 구분 단어 + 뒤 .!? 공백 제거 후 마침표로 정규화
                    s = (parts[i] + parts[i + 1]).strip().rstrip('.!? ')
                    if s:
                        s += '.'
                        sentences.append(s)
                    i += 2
                else:
                    s = parts[i].strip()
                    if s:
                        sentences.append(s)
                    i += 1
            return sentences
    # 기본: .!? 뒤 공백 기준 분리 → 구두점은 앞 문장 끝에 유지됨
    sents = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sents if s.strip() and len(s.strip()) > 1]


def _trim_sentences(text: str, skip: int = 5, delimiters=None) -> str:
    """앞뒤 skip개 문장 제거"""
    sentences = _split_sentences(text, delimiters)
    total = len(sentences)
    if total <= skip * 2:
        return text
    return ' '.join(sentences[skip:total - skip])


def search_popular(keyword: str, count: int = 5) -> list:
    """키워드 인기글 (blog_id, logno) 리스트 반환 (상위 count개)"""
    results = []
    seen = set()
    start = 1
    for _ in range(5):
        if len(results) >= count:
            break
        try:
            text = _get("https://s.search.naver.com/p/review/50/search.naver", {
                "query": keyword, "ssc": "tab.itb.all",
                "sm": "tab_hty.brg", "start": start, "api_type": 5,
            })
            html = json.loads(text)["dom"]["collection"][0]["html"]
        except Exception:
            break
        found = _BLOG_PAT.findall(html)
        if not found:
            break
        for blog_id, logno in found:
            key = (blog_id.lower(), logno)
            if key not in seen:
                seen.add(key)
                results.append((blog_id, logno))
                if len(results) >= count:
                    break
        start += 10
    return results[:count]


def get_post(blog_id: str, logno: str) -> tuple:
    """(제목, 본문텍스트) 반환. 최대 4000자."""
    url = f"https://m.blog.naver.com/{blog_id}/{logno}"
    try:
        html = _get(url)
    except Exception as e:
        return f"{blog_id}/{logno}", f"[수집 실패: {e}]"

    # 제목
    title_m = re.search(r'<title[^>]*>([^<]+)</title>', html, re.I)
    title = title_m.group(1).strip() if title_m else f"{blog_id}/{logno}"
    title = re.sub(r'\s*:?\s*네이버 블로그\s*$', '', title).strip()

    # ── 전략 1: SE3 본문 단락 직접 추출 ────────────────────
    paras = re.findall(
        r'<p[^>]+class="[^"]*se-text-paragraph[^"]*"[^>]*>(.*?)</p>',
        html, re.DOTALL | re.I,
    )
    if paras:
        parts = []
        for p in paras:
            t = _strip_tags(p)
            if t and not _is_noise(t):
                parts.append(t)
        if parts:
            return title, "\n".join(parts)[:4000]

    # ── 전략 2: se-main-container 블록 통째로 추출 ──────────
    m = re.search(
        r'<div[^>]+class="[^"]*se-main-container[^"]*"[^>]*>(.*?)'
        r'(?=<div[^>]+class="[^"]*(?:blog_btn|post_btn|reply|comment)[^"]*")',
        html, re.DOTALL | re.I,
    )
    if not m:
        m = re.search(
            r'<div[^>]+(?:id="postViewArea"|class="[^"]*post_ct[^"]*")[^>]*>(.*?)</div>\s*</div>',
            html, re.DOTALL | re.I,
        )
    if m:
        t = _strip_tags(m.group(1))
        if len(t) > 50:
            lines = [ln for ln in t.splitlines() if not _is_noise(ln.strip())]
            return title, "\n".join(lines)[:4000]

    # ── 전략 3: <p> 태그 중 20자 이상인 것만 수집 ───────────
    all_p = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL | re.I)
    long_parts = []
    for p in all_p:
        t = _strip_tags(p)
        if len(t) > 20 and not _is_noise(t):
            long_parts.append(t)
    if long_parts:
        return title, "\n".join(long_parts)[:4000]

    return title, "[본문 추출 실패]"


def _parse_chunk_range(s: str):
    """'2~4' → (2,4)  /  '3' → (3,3)  /  '0' 또는 빈값 → None"""
    s = s.strip()
    if not s or s == "0":
        return None
    if '~' in s:
        parts = s.split('~', 1)
        try:
            a, b = int(parts[0].strip()), int(parts[1].strip())
            return (min(a, b), max(a, b)) if a > 0 and b > 0 else None
        except ValueError:
            return None
    try:
        n = int(s)
        return (n, n) if n > 0 else None
    except ValueError:
        return None


def _group_sentences(sentences: list, min_size: int, max_size: int) -> list:
    """문장 리스트를 min~max 개씩 묶어 청크 리스트로 반환"""
    import random as _r
    chunks = []
    i = 0
    while i < len(sentences):
        size = _r.randint(min_size, max_size)
        chunk = sentences[i:i + size]
        if chunk:
            chunks.append(' '.join(chunk))
        i += size
    return chunks


def _cut_at_sentence(text: str, maxchars: int) -> str:
    """공백 제외 글자수 기준으로 maxchars 이후 첫 번째 .!? 위치에서 자르기. 0이면 원본 반환."""
    if maxchars <= 0:
        return text
    non_space = sum(1 for c in text if not c.isspace())
    if non_space <= maxchars:
        return text
    # 공백 제외 maxchars번째 문자의 텍스트 내 위치 찾기
    count = 0
    pos = len(text)
    for i, c in enumerate(text):
        if not c.isspace():
            count += 1
            if count >= maxchars:
                pos = i + 1
                break
    m = re.search(r'[.!?]', text[pos:])
    if m:
        return text[:pos + m.end()].strip()
    return text[:pos].strip()


def collect(keyword: str, count: int = 5, skip: int = 0,
            shuffle: bool = True, chunk_range: str = "0",
            maxchars: int = 0, delimiters=None, progress_cb=None) -> list:
    """
    키워드 인기글 수집.
    skip > 0이면 앞뒤 skip개 문장 제거 (.!? 기준).
    shuffle=True이면 모든 포스팅 문장을 합쳐 랜덤 섞기.
    maxchars > 0이면 해당 글자 수 이후 첫 .!? 에서 자르기.
    Returns: [(제목, 본문텍스트, url), ...]  shuffle=True이면 단일 항목 반환
    progress_cb(done, total) 호출 (선택)
    """
    import random as _random
    posts = search_popular(keyword, count)
    results = []
    for i, (blog_id, logno) in enumerate(posts):
        if progress_cb:
            progress_cb(i + 1, len(posts))
        title, text = get_post(blog_id, logno)
        if skip > 0 and not text.startswith("["):
            text = _trim_sentences(text, skip, delimiters)
        url = f"https://blog.naver.com/{blog_id}/{logno}"
        results.append((title, text, url))

    if shuffle and results:
        all_sentences = []
        for _, text, _ in results:
            if not text.startswith("["):
                all_sentences.extend(_split_sentences(text, delimiters))
        # 부유 마침표 최종 정리 (기본/커스텀 경로 공통)
        cleaned = []
        for s in all_sentences:
            s = re.sub(r'(?<!\w)\.\s*', ' ', s)
            s = re.sub(r'\s+', ' ', s).strip()
            if s:
                cleaned.append(s)
        all_sentences = cleaned

        cr = _parse_chunk_range(chunk_range)
        if cr:
            # 단락 단위로 묶어서 셔플
            chunks = _group_sentences(all_sentences, cr[0], cr[1])
            _random.shuffle(chunks)
            body = '\n'.join(chunks)
        else:
            # 0 = 셔플 없이 원본 순서 유지
            body = ' '.join(all_sentences)

        body = _cut_at_sentence(body, maxchars)
        return [("", body, "")]

    return results
