import asyncio
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


async def _do_login(browser, ua):
    """로그인 창 열기 → 완료 감지 → 쿠키는 메모리에만 유지"""
    context = await _make_context(browser, ua)
    page = await context.new_page()
    await page.goto("https://nid.naver.com/nidlogin.login")
    await page.bring_to_front()
    print("[로그인] Chrome 창에서 네이버에 로그인해주세요...")

    for _ in range(300):
        await stopper.sleep(1)
        if stopper.is_set():
            print("[로그인] 중지 요청 — 로그인 취소")
            raise asyncio.CancelledError()
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

    # 로그인은 항상 visible Chrome 창으로
    browser = await playwright.chromium.launch(
        channel="chrome", headless=False, args=["--start-maximized"]
    )
    context = await _do_login(browser, ua)

    if headless:
        # 로그인 후 쿠키 추출 → headless 재시작에 주입
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
