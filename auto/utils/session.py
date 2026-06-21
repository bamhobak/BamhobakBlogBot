import asyncio
import subprocess
from utils import stopper


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


def _get_clipboard():
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
            capture_output=True, text=True, timeout=3,
        )
        return r.stdout.strip()
    except Exception:
        return ""


async def _do_login(browser, ua):
    """로그인 창 열기 → 클립보드 감지로 아이디/비번 자동 입력 → 완료 감지"""
    context = await _make_context(browser, ua)
    page = await context.new_page()
    await page.goto("https://nid.naver.com/nidlogin.login")
    await page.bring_to_front()
    print("[로그인] Chrome 창에서 네이버에 로그인해주세요...")

    prev_clip = await asyncio.to_thread(_get_clipboard)
    filled = 0  # 0=없음, 1=아이디입력됨, 2=비번입력됨

    for _ in range(600):  # 0.5s × 600 = 5분
        await asyncio.sleep(0.5)
        if stopper.is_set():
            print("[로그인] 중지 요청 — 로그인 취소")
            raise asyncio.CancelledError()

        if filled < 2:
            curr = await asyncio.to_thread(_get_clipboard)
            if curr and curr != prev_clip:
                try:
                    if filled == 0:
                        await page.locator('#id').fill(curr)
                    else:
                        await page.locator('#pw').fill(curr)
                        await asyncio.sleep(0.3)
                        await page.locator('button[type=submit]').click()
                    filled += 1
                except Exception:
                    pass
                prev_clip = curr

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
