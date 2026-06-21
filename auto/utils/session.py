import asyncio
import ctypes
import subprocess
import time as _time
from utils import stopper

_VK_CONTROL = 0x11
_VK_V = 0x56


def _ctrl_v_down():
    ctrl = ctypes.windll.user32.GetAsyncKeyState(_VK_CONTROL) & 0x8000
    v = ctypes.windll.user32.GetAsyncKeyState(_VK_V) & 0x8000
    return bool(ctrl and v)


def _get_clipboard():
    """클립보드 텍스트 읽기: ctypes → PowerShell(전체경로) 순 시도"""
    u = ctypes.windll.user32
    k = ctypes.windll.kernel32
    u.GetClipboardData.restype = ctypes.c_void_p
    k.GlobalLock.restype = ctypes.c_void_p
    for _ in range(3):
        try:
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
        _time.sleep(0.02)

    import os
    ps = os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"),
        "System32", "WindowsPowerShell", "v1.0", "powershell.exe",
    )
    try:
        r = subprocess.run(
            [ps, "-NoProfile", "-Command", "Get-Clipboard"],
            capture_output=True, text=True, timeout=5,
            creationflags=0x08000000,
        )
        return r.stdout.strip()
    except Exception as e:
        print(f"[클립보드] PowerShell 오류: {e}")
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


async def _do_login(playwright, browser, ua, headless: bool = True):
    """
    로그인 창 열기 → 외부 창에서 Ctrl+V 감지 → 봇 Chrome에 자동 입력.
    자동 로그인 실패 시 visible Chrome으로 전환해 직접 로그인 가능.
    반환: (context, browser) — fallback 시 browser가 교체된 인스턴스임.
    """
    context = await _make_context(browser, ua)
    page = await context.new_page()
    await page.goto("https://nid.naver.com/nidlogin.login")
    if not headless:
        await page.bring_to_front()

    try:
        await page.wait_for_selector('#id', timeout=10000)
    except Exception:
        pass

    print("[로그인] 아이디를 붙여넣어 주세요. (Ctrl+V)")

    prev_down = False
    filled = 0
    login_click_time = None

    for _ in range(6000):  # 50ms × 6000 = 5분
        await asyncio.sleep(0.05)
        if stopper.is_set():
            print("[로그인] 중지 요청 — 로그인 취소")
            raise asyncio.CancelledError()

        # 로그인 버튼 클릭 후 4초 지나도 nidlogin이면 실패로 판정 → 폴백
        if login_click_time and (_time.time() - login_click_time > 4.0):
            try:
                if "nidlogin" in page.url:
                    print("[로그인] 자동 로그인 실패 — 직접 로그인해주세요.")
                    if headless:
                        old_browser = browser
                        browser = await playwright.chromium.launch(
                            channel="chrome", headless=False, args=["--start-maximized"],
                        )
                        context = await _make_context(browser, ua)
                        page = await context.new_page()
                        await page.goto("https://nid.naver.com/nidlogin.login")
                        await page.bring_to_front()
                        await old_browser.close()
                        headless = False
                    login_click_time = None
                    filled = 0  # Ctrl+V로 재입력 허용
                    print("[로그인] 아이디를 붙여넣어 주세요. (Ctrl+V)")
            except Exception as e:
                print(f"[로그인] fallback 오류: {e}")
                login_click_time = None

        if filled < 2:
            now_down = _ctrl_v_down()
            if now_down and not prev_down:
                await asyncio.sleep(0.05)
                clip = _get_clipboard().strip()
                if clip:
                    try:
                        if filled == 0:
                            await page.locator('#id').fill(clip)
                            print("[로그인] 아이디 입력 완료")
                            print("[로그인] 비밀번호를 붙여넣어 주세요. (Ctrl+V)")
                        else:
                            await page.locator('#pw').fill(clip)
                            print("[로그인] 비번 입력 완료")
                            await asyncio.sleep(0.3)
                            await page.locator('button[type=submit]').click()
                            login_click_time = _time.time()
                        filled += 1
                    except Exception as e:
                        print(f"[로그인] 입력 오류: {e}")
            prev_down = now_down

        if "naver.com" in page.url and "nidlogin" not in page.url:
            break
    else:
        raise TimeoutError("5분 내 로그인하지 않아 종료합니다.")

    await page.close()
    print("[로그인] 완료.")
    return context, browser


async def launch_browser(playwright, headless: bool = True, **_):
    """
    매 실행마다 로그인 필요. 세션 파일 저장 없음.
    headless=True → 로그인(headless) 후 headless로 재시작.
    자동 로그인 실패 시 visible 창 전환 후 직접 로그인 대기.
    """
    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    browser = await playwright.chromium.launch(
        channel="chrome", headless=headless, args=["--start-maximized"],
    )
    context, browser = await _do_login(playwright, browser, ua, headless=headless)

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
