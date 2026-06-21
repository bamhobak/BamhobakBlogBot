"""
봇 시작 시점의 Chrome PID를 스냅샷해 두고,
그 PID들이 모두 사라지면 stopper.request()로 봇을 중지한다.
psutil 없어도 Windows tasklist 명령으로 동작한다.
"""
import subprocess
import threading
import time

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

_CHROME_NAMES = {"chrome.exe", "chrome"}


def _chrome_pids() -> set:
    if _HAS_PSUTIL:
        try:
            return {
                p.pid for p in psutil.process_iter(["pid", "name"])
                if (p.info["name"] or "").lower() in _CHROME_NAMES
            }
        except Exception:
            pass

    # psutil 없으면 tasklist 사용 (Windows 내장)
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5,
        )
        pids = set()
        for line in result.stdout.strip().splitlines():
            parts = line.strip().strip('"').split('","')
            if len(parts) >= 2:
                try:
                    pids.add(int(parts[1]))
                except ValueError:
                    pass
        return pids
    except Exception:
        return set()


def start(sw=None) -> bool:
    """
    봇 시작 전에 호출.
    현재 실행 중인 Chrome PID를 스냅샷하고 감시 스레드를 시작한다.
    """
    user_pids = _chrome_pids()

    if not user_pids:
        if sw:
            sw.update("[크롬감시] 실행 중인 Chrome 없음 — 감시 생략")
        return False

    if sw:
        sw.update(f"[크롬감시] 개인 Chrome {len(user_pids)}개 감지 — 종료 시 봇 자동 중지")

    def _watch():
        from utils import stopper
        while not stopper.is_set():
            alive = _chrome_pids()
            if not any(pid in alive for pid in user_pids):
                if sw:
                    sw.update("[크롬감시] 개인 Chrome 종료 감지 → 봇 중지")
                stopper.request()
                break
            time.sleep(2)

    threading.Thread(target=_watch, daemon=True).start()
    return True
