import asyncio
import ctypes
import subprocess
from utils import stopper

_VK_CONTROL = 0x11
_VK_V = 0x56


def _ctrl_v_down():
    """전역 Ctrl+V 키 상태 확인"""
    ctrl = ctypes.windll.user32.GetAsyncKeyState(_VK_CONTROL) & 0x8000
    v = ctypes.windll.user32.GetAsyncKeyState(_VK_V) & 0x8000
    return bool(ctrl and v)


def _get_clipboard():
    """클립보드 텍스트 읽기: ctypes → PowerShell 순 시도"""
    try:
        u = ctypes.windll.user32
        k = ctypes.windll.kernel32
        u.GetClipboardData.restype = ctypes.c_void_p
        k.GlobalLock.restype = ctypes.c_void_p
        if u.OpenClipboard(None):
            try:
                h = u.GetClipboardData(13)  # CF_UNICODETEXT
                if h:
                    p = k.GlobalLock(h)
                    if p:
                        try:
                            return ctypes.wstring_at(p)
                        finally:
                            k.GlobalUnlock(h)
            finally:
                u.CloseClipboard()
    except Exception:
        pass
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
            capture_output=True, text=True, timeout=3,
            creationflags=0x08000000,
        )
        return r.stdout.strip()
    except Exception:
        return ""


async def _apply_stealth(context):
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['ko-KR','ko','en-US','en'] });
        window.chrome = { runtime: {} };
    """)


async def _make_context(browser, ua):
    ctx = await browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent=ua,
        locale="ko-KR",
        timezone_id="Asia/Seoul",
    )
    await _apply_stealth(ctx)
    return ctx


async def _do_login(browser, ua):
    """로그인 창 열기 → 외부 창에서 Ctrl+V 감지 → 봇 Chrome에 자동 입력"""
    context = await _make_context(browser, ua)
    page = await context.new_page()
    await page.goto("https://nid.naver.com/nidlogin.login")
    await page.bring_to_front()

    try:
        await page.wait_for_selector('#id', timeout=10000)
    except Exception:
        pass

    print("[로그인] Chrome 창에서 네이버에 로그인해주세요...")

    prev_down = False
    filled = 0

    for _ in range(6000):  # 50ms × 6000 = 5분
        await asyncio.sleep(0.05)
        if stopper.is_set():
            print("[로그인] 중지 요청 — 로그인 취소")
            raise asyncio.CancelledError()

        if filled < 2:
            now_down = _ctrl_v_down()
            if now_down and not prev_down:
                await asyncio.sleep(0.05)  # 클립보드 확정 대기
                clip = _get_clipboard().strip()
                if clip:
                    try:
                        if filled == 0:
                            await page.locator('#id').fill(clip)
                        else:
                            await page.locator('#pw').fill(clip)
                            await asyncio.sleep(0.3)
                            await page.locator('button[type=submit]').click()
                        filled += 1
                    except Exception:
                        pass
            prev_down = now_down

        if "naver.com" in page.url and "nidlogin" not in page.url:
            break
    else:
        raise TimeoutError("5분 내 로그인하지 않아 종료합니다.")

    await page.close()
    print("[로그인] 완료. (세션 파일 미저장 — 종료 시 자동 소멸)")
    return context


async def launch_browser(playwright, headless: bool = True, **_):
    """
    매 실행마다 로그인 필요. 세션 파일 저장 없음.
    headless=True → 로그인(visible) 후 headless로 재시작.
    """
    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    browser = await playwright.chromium.launch(
        channel="chrome", headless=False, args=["--start-maximized"]
    )
    context = await _do_login(browser, ua)

    if headless:
        state = await context.storage_state()
        await browser.close()

        browser = await playwright.chromium.launch(
            channel="chrome", headless=True, args=["--start-maximized"]
        )
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=ua,
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            storage_state=state,
        )
        await _apply_stealth(ctx)
        context = ctx

    return browser, context
