import random
from utils import stopper

_DWELL_RANGE: tuple | None = None  # None = 액션별 기본값 사용


def set_dwell(min_sec: float, max_sec: float):
    global _DWELL_RANGE
    _DWELL_RANGE = (min_sec, max_sec)


async def delay(min_sec=1.0, max_sec=3.0):
    await stopper.sleep(random.uniform(min_sec, max_sec))


async def slow_scroll(page, times=3):
    try:
        scroll_h = await page.evaluate("document.body.scrollHeight")
        vh = await page.evaluate("window.innerHeight") or 900
    except Exception:
        scroll_h, vh = 3600, 900

    step_min = int(vh * 0.45)
    step_max = int(vh * 0.75)

    scrollable = max(0, scroll_h - vh)
    avg_step = (step_min + step_max) // 2
    needed = max(times, round(scrollable / avg_step)) if avg_step else times
    effective = min(needed, times * 2, 12)

    reached_bottom = False

    for _ in range(effective):
        if stopper.is_set():
            break

        try:
            current_y = await page.evaluate("window.scrollY")
        except Exception:
            current_y = 0

        near_bottom = scrollable > 0 and current_y >= scrollable * 0.88

        if near_bottom and not reached_bottom:
            reached_bottom = True
            # 바닥 도달 → 위로 30~60% 되돌리기
            up = random.randint(int(scrollable * 0.3), int(scrollable * 0.6))
            await page.mouse.wheel(0, -up)
        elif not near_bottom and random.random() < 0.15 and current_y > vh:
            # 중간 중간 잠깐 위로 올렸다가 (재독)
            up = random.randint(int(vh * 0.2), int(vh * 0.4))
            await page.mouse.wheel(0, -up)
            await stopper.sleep(random.uniform(0.3, 0.7))
            await page.mouse.wheel(0, random.randint(step_min, step_max))
        else:
            await page.mouse.wheel(0, random.randint(step_min, step_max))

        await stopper.sleep(random.uniform(0.5, 1.5))


async def read_pause(min_sec=3.0, max_sec=8.0):
    if _DWELL_RANGE is not None:
        mn, mx = _DWELL_RANGE
    else:
        mn, mx = min_sec, max_sec
    await stopper.sleep(random.uniform(mn, mx))


async def random_hover(page):
    if stopper.is_set():
        return
    x = random.randint(200, 900)
    y = random.randint(200, 600)
    await page.mouse.move(x, y)
    await stopper.sleep(random.uniform(0.3, 0.8))
