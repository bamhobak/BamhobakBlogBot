"""
Chrome Remote Debugging Protocol 설정 유틸리티.
Chrome 바로가기에 --remote-debugging-port=9222를 추가해
Playwright가 사용자 Chrome에 CDP로 연결할 수 있도록 한다.
"""
import os
import socket
import subprocess

DEBUG_PORT = 9222
_FLAG = f"--remote-debugging-port={DEBUG_PORT}"


def is_cdp_available() -> bool:
    """Chrome이 CDP 포트를 열고 있는지 확인"""
    try:
        s = socket.create_connection(("127.0.0.1", DEBUG_PORT), timeout=1)
        s.close()
        return True
    except OSError:
        return False


def _find_shortcuts() -> list:
    candidates = [
        os.path.join(os.environ.get("USERPROFILE", ""), "Desktop", "Google Chrome.lnk"),
        os.path.join(os.environ.get("APPDATA", ""),
                     "Microsoft", "Windows", "Start Menu", "Programs", "Google Chrome.lnk"),
        os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Desktop", "Google Chrome.lnk"),
    ]
    return [p for p in candidates if os.path.exists(p)]


def is_flag_set() -> bool:
    """Chrome 바로가기에 이미 CDP 플래그가 있는지 확인"""
    shortcuts = _find_shortcuts()
    if not shortcuts:
        return False
    checks = "\n".join(
        f'$sc = $ws.CreateShortcut("{s.replace(chr(92), chr(92)*2)}"); '
        f'if ($sc.Arguments -like "*remote-debugging-port*") {{ Write-Output "yes"; exit }}'
        for s in shortcuts
    )
    script = f'$ws = New-Object -ComObject WScript.Shell\n{checks}\nWrite-Output "no"'
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True, text=True, timeout=10,
    )
    return "yes" in r.stdout.lower()


def setup_shortcut() -> tuple[int, list]:
    """
    Chrome 바로가기에 --remote-debugging-port=9222 추가.
    Returns: (수정된 개수, 수정된 경로 목록)
    """
    shortcuts = _find_shortcuts()
    if not shortcuts:
        return 0, []

    lines = ["$ws = New-Object -ComObject WScript.Shell", "$n = 0", "$done = @()"]
    for s in shortcuts:
        se = s.replace("\\", "\\\\")
        lines += [
            f'$sc = $ws.CreateShortcut("{se}")',
            f'if ($sc.Arguments -notlike "*remote-debugging-port*") {{',
            f'    $sc.Arguments = ($sc.Arguments + " {_FLAG}").Trim()',
            f'    $sc.Save()',
            f'    $n++',
            f'    $done += "{se}"',
            f'}}',
        ]
    lines += ["Write-Output $n", 'Write-Output ($done -join "|")']

    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "\n".join(lines)],
        capture_output=True, text=True, timeout=10,
    )
    out = r.stdout.strip().splitlines()
    count = int(out[0]) if out else 0
    paths = out[1].split("|") if len(out) > 1 and out[1] else []
    return count, paths
