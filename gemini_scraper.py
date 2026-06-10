"""
Gemini 웹 스크래퍼
- Playwright 전용 스레드를 하나 유지 (스레드 안전)
- 다른 스레드에서 query() 호출 시 큐로 전달하고 결과 대기
"""
import os
import sys
import time
import threading
import queue as _queue
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# Playwright headless shell 경로를 탐색 (CCleaner 회피: chrome-headless-shell.exe 사용)
def _find_headless_shell() -> str:
    candidates = []
    # 1순위: exe 옆 ms-playwright
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(base, "ms-playwright"))
    # 2순위: AppData ms-playwright
    candidates.append(os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright"))
    for ms_dir in candidates:
        if not os.path.exists(ms_dir):
            continue
        try:
            for entry in sorted(os.listdir(ms_dir), reverse=True):
                if entry.startswith("chromium_headless_shell"):
                    for root, _, files in os.walk(os.path.join(ms_dir, entry)):
                        if "chrome-headless-shell.exe" in files:
                            return os.path.join(root, "chrome-headless-shell.exe")
        except Exception:
            pass
    return ""

_HEADLESS_SHELL = _find_headless_shell()

_URL = "https://gemini.google.com/"

_INPUT_SELS = [
    'div[contenteditable="true"][data-placeholder]',
    'rich-textarea div[contenteditable="true"]',
    'div.ql-editor[contenteditable="true"]',
    'p[data-placeholder]',
    'textarea',
]

_RESP_SELS = [
    'message-content .markdown',
    '.response-container-content',
    'model-response .markdown',
    '.markdown.markdown-main-panel',
    'div.response-content',
    '[data-message-author-role="model"] .markdown',
]

# ── 전용 스레드 상태 ──────────────────────────────────
_task_queue       = _queue.Queue()
_worker_thread    = None
_is_running       = False
_cached_input_sel = None


def start():
    """Playwright 전용 스레드를 시작합니다."""
    global _worker_thread, _is_running
    if _is_running and _worker_thread and _worker_thread.is_alive():
        return
    _is_running = True
    _worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="PlaywrightWorker")
    _worker_thread.start()
    # 브라우저가 준비될 때까지 대기 (최대 30초)
    _submit_task("__ping__", timeout_sec=30)


def stop():
    """전용 스레드를 종료합니다."""
    global _is_running
    _is_running = False
    _task_queue.put(None)  # 종료 신호


def is_connected() -> bool:
    return _is_running and _worker_thread is not None and _worker_thread.is_alive()


def query(prompt: str, timeout_sec: int = 50, cancel_event=None) -> str:
    """Gemini에 프롬프트를 전송하고 응답을 반환합니다."""
    if not is_connected():
        raise RuntimeError("브라우저가 연결되지 않았습니다. 크롬 로드 버튼을 눌러 주세요.")
    return _submit_task(prompt, timeout_sec, cancel_event=cancel_event)


# ── 내부 구현 ─────────────────────────────────────────

def _submit_task(prompt: str, timeout_sec: int, cancel_event=None) -> str:
    """태스크를 큐에 넣고 결과를 기다립니다."""
    result_event = threading.Event()
    result_box   = [None, None]  # [status, value]
    _task_queue.put((prompt, timeout_sec, result_event, result_box))
    deadline = time.time() + timeout_sec + 30
    # cancel_event를 0.3초마다 확인하며 대기
    while time.time() < deadline:
        if cancel_event is not None and cancel_event.is_set():
            result_box[0], result_box[1] = "err", "중단됨"
            break
        if result_event.wait(timeout=0.3):
            break
    status, value = result_box
    if status == "err":
        raise RuntimeError(value)
    return value or ""


def _worker_loop():
    """Playwright 전용 스레드 메인 루프."""
    global _is_running
    page = None

    _LAUNCH_ARGS = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ]

    with sync_playwright() as pw:
        browser = None
        # 1순위: chrome-headless-shell.exe 직접 지정 (CCleaner 미탐지)
        if _HEADLESS_SHELL:
            try:
                browser = pw.chromium.launch(
                    executable_path=_HEADLESS_SHELL,
                    headless=True, args=_LAUNCH_ARGS)
            except Exception:
                pass
        # 2순위: 시스템 Chrome/Edge 폴백
        if browser is None:
            for channel in ("chrome", "msedge"):
                try:
                    browser = pw.chromium.launch(channel=channel, headless=True, args=_LAUNCH_ARGS)
                    break
                except Exception:
                    continue
        try:
            page = _open_gemini(browser)

            while _is_running:
                try:
                    task = _task_queue.get(timeout=0.5)
                except _queue.Empty:
                    continue

                if task is None:  # 종료 신호
                    break

                prompt, timeout_sec, result_event, result_box = task

                if prompt == "__ping__":
                    result_box[0], result_box[1] = "ok", "ready"
                    result_event.set()
                    continue

                try:
                    _new_chat(page)
                    text = _do_query(page, prompt, timeout_sec)
                    result_box[0], result_box[1] = "ok", text
                except Exception as e:
                    result_box[0], result_box[1] = "err", str(e)
                    # 페이지 리셋 시도
                    try:
                        page = _open_gemini(browser)
                    except Exception:
                        pass
                finally:
                    result_event.set()

        finally:
            try:
                browser.close()
            except Exception:
                pass
            _is_running = False


def _open_gemini(browser) -> object:
    """새 컨텍스트로 Gemini 페이지를 엽니다."""
    ctx = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
    )
    page = ctx.new_page()
    page.goto(_URL, wait_until="domcontentloaded", timeout=30000)
    _wait(2)
    _dismiss_popups(page)
    return page


def _new_chat(page):
    """새 채팅을 시작합니다."""
    for sel in [
        'button[aria-label*="New chat"]',
        'button[aria-label*="새 채팅"]',
        'mat-icon:has-text("edit_square")',
    ]:
        try:
            page.locator(sel).first.click(timeout=1000)
            _wait(0.5)
            return
        except PWTimeout:
            continue
    # 버튼 못 찾으면 URL 재접속
    try:
        page.goto(_URL, wait_until="domcontentloaded", timeout=15000)
        _wait(1.0)
        _dismiss_popups(page)
    except Exception:
        pass


def _do_query(page, prompt: str, timeout_sec: int) -> str:
    """실제 쿼리 실행."""
    input_el = _find_input(page)
    if input_el is None:
        page.goto(_URL, wait_until="domcontentloaded", timeout=15000)
        _wait(2)
        _dismiss_popups(page)
        input_el = _find_input(page)
        if input_el is None:
            raise RuntimeError("Gemini 입력창을 찾을 수 없습니다.")

    input_el.click()
    _wait(0.15)
    input_el.fill(prompt)
    _wait(0.1)
    page.keyboard.press("Enter")

    _wait_for_response(page, timeout_sec)
    return _extract_response(page)


def _find_input(page):
    global _cached_input_sel
    # 캐시된 셀렉터 먼저 시도
    if _cached_input_sel:
        try:
            el = page.locator(_cached_input_sel).first
            if el.is_visible():
                return el
        except Exception:
            _cached_input_sel = None
    # 순서대로 탐색
    for sel in _INPUT_SELS:
        try:
            page.wait_for_selector(sel, timeout=2000)
            el = page.locator(sel).first
            if el.is_visible():
                _cached_input_sel = sel
                return el
        except PWTimeout:
            continue
    return None


def _dismiss_popups(page):
    for text in ["동의", "I agree", "Accept", "Agree", "확인", "OK"]:
        try:
            page.locator(f"button:has-text('{text}')").first.click(timeout=1000)
            _wait(0.3)
        except PWTimeout:
            pass


def _wait_for_response(page, timeout_sec: int):
    stop_sel = 'button[aria-label*="Stop"], button[aria-label*="중지"]'
    # stop 버튼 나타날 때까지 최대 5초 대기
    try:
        page.wait_for_selector(stop_sel, timeout=8000)
    except PWTimeout:
        # stop 버튼 못 찾으면 짧게 버퍼 후 반환
        _wait(0.5)
        return
    # stop 버튼이 사라질 때까지 0.3초 간격 폴링
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            if not page.locator(stop_sel).is_visible():
                break
        except Exception:
            break
        _wait(0.3)
    else:
        raise RuntimeError("응답 시간 초과")
    _wait(0.5)


_GEMINI_ERR_PATTERNS = [
    "Something went wrong",
    "문제가 발생했습니다",
    "오류가 발생했어요",
]


def _check_gemini_error(text: str):
    for pat in _GEMINI_ERR_PATTERNS:
        if pat.lower() in text.lower():
            raise RuntimeError("gemini_server_error")


def _extract_response(page) -> str:
    for sel in _RESP_SELS:
        try:
            els = page.locator(sel).all()
            if els:
                html = els[-1].inner_html(timeout=5000).strip()
                if len(html) > 20:
                    try:
                        import os
                        dbg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_debug_html.txt")
                        open(dbg, "w", encoding="utf-8").write(html[:8000])
                    except Exception:
                        pass
                    md = _html_to_markdown(html)
                    _check_gemini_error(md)
                    return md
        except RuntimeError:
            raise
        except Exception:
            continue
    text = page.inner_text("body")
    if text and len(text) > 50:
        _check_gemini_error(text)
        return text
    raise RuntimeError("응답을 추출하지 못했습니다.")


def _html_to_markdown(html: str) -> str:
    """Gemini HTML 응답을 마크다운으로 변환합니다."""
    from html.parser import HTMLParser

    class _Conv(HTMLParser):
        def __init__(self):
            super().__init__()
            self.out = []
            self._stack = []
            self._bq_depth = 0
            self._li_depth = 0
            self._list_type_stack = []  # 'ol' | 'ul' per nesting level
            self._ol_counters     = []  # item counter per ol level
            self._prev_ol_counter = 0   # 이전 <ol> 닫힐 때의 카운터 (연속 <ol> 대응)

        def _in_bq(self): return self._bq_depth > 0
        def _in_li(self): return self._li_depth > 0
        def _in_ol(self):
            return bool(self._list_type_stack) and self._list_type_stack[-1] == 'ol'

        def _reset_ol_seq(self):
            self._prev_ol_counter = 0

        def handle_starttag(self, tag, attrs):
            self._stack.append(tag)
            t = tag.lower()

            if t == 'h1':
                self._reset_ol_seq(); self.out.append('\n# ')
            elif t == 'h2':
                self._reset_ol_seq(); self.out.append('\n## ')
            elif t == 'h3':
                self._reset_ol_seq(); self.out.append('\n### ')
            elif t == 'h4':
                self._reset_ol_seq(); self.out.append('\n#### ')
            elif t == 'hr':
                self._reset_ol_seq(); self.out.append('\n---\n')
            elif t == 'br': self.out.append('\n')
            elif t in ('strong', 'b'): self.out.append('**')
            elif t in ('em', 'i'):     self.out.append('*')
            elif t == 'blockquote':
                self._reset_ol_seq()
                self._bq_depth += 1
            elif t in ('ul', 'ol'):
                self._reset_ol_seq()
                self._list_type_stack.append('ul')  # ol도 ul과 동일하게 처리
                self._ol_counters.append(0)
            elif t == 'li':
                self._li_depth += 1
                self.out.append('\n- ')
            elif t == 'p':
                if self._in_bq():
                    self.out.append('\n> ')
                elif self._in_li():
                    pass
                else:
                    self._reset_ol_seq()
                    self.out.append('\n')
            elif t == 'div':
                if not self._in_bq() and not self._in_li():
                    self._reset_ol_seq()
                    self.out.append('\n')
            elif t == 'code': self.out.append('`')

        def handle_endtag(self, tag):
            if self._stack and self._stack[-1] == tag:
                self._stack.pop()
            t = tag.lower()
            if t in ('h1', 'h2', 'h3', 'h4'): self.out.append('\n')
            elif t in ('strong', 'b'): self.out.append('**')
            elif t in ('em', 'i'):     self.out.append('*')
            elif t == 'code':          self.out.append('`')
            elif t == 'blockquote':
                self._bq_depth = max(0, self._bq_depth - 1)
                self.out.append('\n')
            elif t in ('ul', 'ol'):
                if self._list_type_stack:
                    self._list_type_stack.pop()
                    self._ol_counters.pop()
                self.out.append('\n')
            elif t == 'li':
                self._li_depth = max(0, self._li_depth - 1)
                self.out.append('\n')
            elif t in ('p', 'div'): self.out.append('\n')

        def handle_data(self, data):
            self.out.append(data)

        def handle_entityref(self, name):
            import html as _h
            self.out.append(_h.unescape(f'&{name};'))

        def handle_charref(self, name):
            import html as _h
            self.out.append(_h.unescape(f'&#{name};'))

    conv = _Conv()
    conv.feed(html)
    md = ''.join(conv.out)
    # 연속 빈 줄 정리
    import re as _re
    md = _re.sub(r'\n{3,}', '\n\n', md)
    return md.strip()


def _wait(sec: float):
    time.sleep(sec)
