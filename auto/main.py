"""
naver-auto v1.0.16
네이버 개인 업무 자동화 — 상태창 중지 버튼으로 종료
"""

import os
import sys

if getattr(sys, "frozen", False):
    _base = os.path.dirname(sys.executable)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(_base, "playwright_browsers")

import asyncio
import random

import yaml
from playwright.async_api import async_playwright

from utils.session import launch_browser
from utils.status import StatusWindow
from utils import stopper
from actions.mail import check_mail
from actions.news import browse_news
from actions.search import do_search
from actions.home import browse_home
from actions.blog import browse_blog
from actions.kin import browse_kin
from actions.shopping import browse_shopping
from actions.weather import check_weather
from actions.finance import browse_finance


def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def load_config():
    env_cfg = os.environ.get("AUTO_CONFIG_PATH", "")
    candidates = []
    if env_cfg and os.path.exists(env_cfg):
        candidates.append(env_cfg)
    candidates.append(os.path.join(get_base_dir(), "config.yaml"))
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(os.path.join(sys._MEIPASS, "config.yaml"))
    for path in candidates:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f)
    raise FileNotFoundError(f"config.yaml 없음: {candidates[-1]}")


def _pick(val, def_min, def_max):
    if isinstance(val, dict):
        return random.randint(val.get("min", def_min), val.get("max", def_max))
    return val if val is not None else def_min


def build_action_pool(page, cfg, keywords=None):
    sc = cfg["scenario"]
    if keywords is None:
        keywords = cfg.get("keywords", [])
    act = cfg.get("actions", {})
    pool = []
    if act.get("home", True):     pool.append((3, "홈 탐색",     lambda: browse_home(page)))
    if act.get("search", True):   pool.append((3, "키워드 검색", lambda: do_search(page, keywords=keywords, click_count=_pick(sc.get("search_click_count"), 2, 4))))
    if act.get("news", True):     pool.append((3, "뉴스 읽기",   lambda: browse_news(page, article_count=_pick(sc.get("news_article_count"), 2, 5))))
    if act.get("blog", True):     pool.append((2, "블로그 검색", lambda: browse_blog(page, keywords=keywords)))
    if act.get("mail", True):     pool.append((2, "메일 확인",   lambda: check_mail(page, read_count=_pick(sc.get("mail_read_count"), 1, 3))))
    if act.get("kin", True):      pool.append((2, "지식iN",      lambda: browse_kin(page, keywords=keywords)))
    if act.get("shopping", True): pool.append((1, "쇼핑 탐색",   lambda: browse_shopping(page)))
    if act.get("weather", True):  pool.append((1, "날씨 확인",   lambda: check_weather(page)))
    if act.get("finance", True):  pool.append((1, "증권 확인",   lambda: browse_finance(page)))
    return pool or [(1, "홈 탐색", lambda: browse_home(page))]


def pick_actions(pool, count):
    weights = [w for w, _, _ in pool]
    chosen = random.choices(pool, weights=weights, k=count)
    seen = set()
    unique = []
    for item in chosen:
        key = id(item[2])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


async def main(headless: bool, sw: StatusWindow):
    from utils.human import set_dwell
    from utils.keywords import get_run_keywords
    cfg = load_config()
    sc = cfg["scenario"]
    delay_cfg = sc["between_action_delay"]
    round_num = 0

    dwell = sc.get("page_dwell", {})
    if dwell:
        set_dwell(float(dwell.get("min", 4)), float(dwell.get("max", 12)))

    kw_count = sc.get("keyword_count", 20)

    stopper.init(asyncio.get_event_loop())

    async with async_playwright() as pw:
        # 로그인 전: 임시 헤드리스 브라우저로 DataLab 키워드 수집
        run_keywords = await get_run_keywords(pw, cfg.get("keywords", []), kw_count)

        browser, context = await launch_browser(pw, headless=headless)
        page = await context.new_page()

        try:
            while not stopper.is_set():
                round_num += 1
                pool = build_action_pool(page, cfg, run_keywords)
                count = random.randint(2, 4)
                actions = pick_actions(pool, count)
                random.shuffle(actions)

                sw.update(f"라운드 {round_num} 시작 ({len(actions)}개 액션)")

                for weight, label, action_fn in actions:
                    if stopper.is_set():
                        break
                    sw.update(f"[라운드 {round_num}] {label} 중...")
                    try:
                        await action_fn()
                    except Exception as e:
                        sw.update(f"[오류] {label}: {e}")

                    wait = random.uniform(delay_cfg["min"], delay_cfg["max"])
                    sw.update(f"[라운드 {round_num}] 다음 액션까지 {wait:.0f}초 대기")
                    await stopper.sleep(wait)

                if stopper.is_set():
                    break

                rest = random.uniform(sc["round_rest"]["min"], sc["round_rest"]["max"])
                sw.update(f"라운드 {round_num} 완료 — {rest:.0f}초 휴식 중")
                await stopper.sleep(rest)

        finally:
            sw.update("종료 중...")
            await browser.close()
            sw.close()


if __name__ == "__main__":
    try:
        cfg = load_config()
        headless = cfg.get("browser", {}).get("headless", True)

        sw = StatusWindow()
        sw.redirect_print()
        asyncio.run(main(headless=headless, sw=sw))
    except Exception as e:
        import tkinter.messagebox as mb
        mb.showerror("오류", str(e))
