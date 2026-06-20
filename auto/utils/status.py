import tkinter as tk
from tkinter import scrolledtext
import threading
import queue
import time
import sys


class StatusWindow:
    def __init__(self):
        self._queue = queue.Queue()
        self._start = time.time()
        self.stop_requested = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # ── 외부에서 호출 ────────────────────────────────────────────────────────
    def log(self, text: str, level: str = "info"):
        """level: info | success | error | warn | wait | action"""
        self._queue.put(("log", text, level))

    def update(self, text: str):
        """main.py 호환용"""
        level = _classify(text)
        self.log(text, level)

    def redirect_print(self):
        """print() 출력을 상태창으로 리다이렉트"""
        sw = self

        class _Writer:
            def write(self, s):
                s = s.rstrip("\n").strip()
                if s:
                    sw.log(s, _classify(s))

            def flush(self):
                pass

        sys.stdout = _Writer()

    def close(self):
        self._queue.put(("close",))

    # ── 내부 tkinter 스레드 ──────────────────────────────────────────────────
    def _run(self):
        root = tk.Tk()
        root.title("네이버 자동화 로그")
        root.geometry("420x160+10+10")
        root.attributes("-topmost", True)
        root.resizable(True, False)
        root.configure(bg="#1e1e2e")
        # ── 로그 텍스트 ───────────────────────────────────────────────────
        log_box = scrolledtext.ScrolledText(
            root, bg="#181825", fg="#cdd6f4",
            font=("Consolas", 9), state="disabled",
            relief="flat", padx=6, pady=4,
            wrap="word", height=7
        )
        log_box.pack(fill="both", expand=True, padx=0, pady=0)

        # 색상 태그
        log_box.tag_config("error",   foreground="#f38ba8")
        log_box.tag_config("success", foreground="#a6e3a1")
        log_box.tag_config("warn",    foreground="#f9e2af")
        log_box.tag_config("wait",    foreground="#6c7086")
        log_box.tag_config("action",  foreground="#89b4fa")
        log_box.tag_config("info",    foreground="#cdd6f4")

        # ── 하단 한 줄: 상태 + 시간 + 중지 버튼 ─────────────────────────
        footer = tk.Frame(root, bg="#313244")
        footer.pack(fill="x")

        status_var = tk.StringVar(value="● 실행 중")
        tk.Label(footer, textvariable=status_var,
                 bg="#313244", fg="#a6e3a1",
                 font=("맑은 고딕", 9, "bold")).pack(side="left", padx=10, pady=5)

        time_var = tk.StringVar(value="00:00:00")
        tk.Label(footer, textvariable=time_var,
                 bg="#313244", fg="#6c7086",
                 font=("맑은 고딕", 9)).pack(side="left", padx=(0, 10), pady=5)

        def on_stop():
            self.stop_requested.set()
            from utils import stopper
            stopper.request()
            status_var.set("● 종료 중...")
            stop_btn.config(state="disabled", text="종료 중...")
            _append(log_box, "중지 요청 — 즉시 종료합니다.", "warn")

        root.protocol("WM_DELETE_WINDOW", on_stop)

        stop_btn = tk.Button(footer, text="■  중지",
                             command=on_stop,
                             bg="#f38ba8", fg="#1e1e2e",
                             activebackground="#e06c75", activeforeground="#1e1e2e",
                             font=("맑은 고딕", 9, "bold"),
                             relief="flat", cursor="hand2",
                             padx=14, pady=2)
        stop_btn.pack(side="right", padx=10, pady=4)

        # ── 틱 루프 ───────────────────────────────────────────────────────
        def tick():
            elapsed = int(time.time() - self._start)
            h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
            time_var.set(f"{h:02d}:{m:02d}:{s:02d}")
            try:
                while True:
                    item = self._queue.get_nowait()
                    if item[0] == "log":
                        _, text, level = item
                        ts = _ts(self._start)
                        _append(log_box, f"[{ts}] {text}", level)
                    elif item[0] == "close":
                        root.destroy()
                        return
            except queue.Empty:
                pass
            root.after(300, tick)

        root.after(300, tick)
        root.mainloop()


# ── 헬퍼 ────────────────────────────────────────────────────────────────────

def _ts(start: float) -> str:
    e = int(time.time() - start)
    return f"{e//3600:02d}:{(e%3600)//60:02d}:{e%60:02d}"


def _append(box: scrolledtext.ScrolledText, text: str, level: str):
    box.config(state="normal")
    box.insert("end", text + "\n", level)
    # 최대 200줄 유지
    lines = int(box.index("end-1c").split(".")[0])
    if lines > 200:
        box.delete("1.0", f"{lines - 200}.0")
    box.see("end")
    box.config(state="disabled")


def _classify(text: str) -> str:
    t = text.lower()
    if "[오류]" in text or "error" in t or "실패" in text or "오류" in text:
        return "error"
    if "완료" in text and "오류" not in text:
        return "success"
    if "[대기]" in text or "[휴식]" in text or "초 대기" in text or "초 휴식" in text:
        return "wait"
    if any(x in text for x in ["[라운드", "==="]):
        return "action"
    if "[로그인]" in text or "[세션]" in text or "[시작]" in text or "중지" in text:
        return "warn"
    return "info"
