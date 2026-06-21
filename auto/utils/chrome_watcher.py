"""
봇 시작 시점의 Chrome 루트 프로세스 PID를 스냅샷해 두고,
그 PID들이 모두 사라지면 stopper.request()로 봇을 중지한다.
루트 프로세스(부모가 chrome.exe가 아닌 것)만 추적해 오감지를 방지한다.
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


def _chrome_root_pids() -> set:
    """Chrome 브라우저 루트 프로세스 PID만 반환 (렌더러·GPU 등 자식 제외)."""
    if _HAS_PSUTIL:
        try:
            all_chrome = {
                p.pid for p in psutil.process_iter(["pid", "name"])
                if (p.info["name"] or "").lower() in _CHROME_NAMES
            }
            root = set()
            for p in psutil.process_iter(["pid", "name", "ppid"]):
                if p.pid in all_chrome:
                    if p.info.get("ppid") not in all_chrome:
                        root.add(p.pid)
            return root
        except Exception:
            pass

    # psutil 없으면 tasklist 전체 PID 사용 (오감지 가능성 있으나 차선책)
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
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
    현재 실행 중인 Chrome 루트 PID를 스냅샷하고 감시 스레드를 시작한다.
    """
    user_pids = _chrome_root_pids()

    if not user_pids:
        if sw:
            sw.update("[크롬감시] 실행 중인 Chrome 없음 — 감시 생략")
        return False

    if sw:
        sw.update(f"[크롬감시] 개인 Chrome {len(user_pids)}개 감지 — 종료 시 봇 자동 중지")

    def _watch():
        from utils import stopper
        while not stopper.is_set():
            alive = _chrome_root_pids()
            if not any(pid in alive for pid in user_pids):
                if sw:
                    sw.update("[크롬감시] 개인 Chrome 종료 감지 → 봇 중지")
                stopper.request()
                break
            time.sleep(2)

    threading.Thread(target=_watch, daemon=True).start()
    return True
