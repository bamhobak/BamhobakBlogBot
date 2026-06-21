"""
Chrome 쿠키 추출 — Chrome이 열린 상태에서도 작동
DPAPI + AES-GCM 복호화 (pywin32 없이 ctypes 사용)
"""

import base64
import ctypes
import ctypes.wintypes
import json
import os
import shutil
import sqlite3
import tempfile


# ── DPAPI 복호화 (ctypes 직접 호출) ──────────────────────────────────────────

class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi_decrypt(data: bytes) -> bytes:
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _BLOB(ctypes.sizeof(buf), buf)
    blob_out = _BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise ctypes.WinError()
    result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return result


# ── AES-GCM 복호화 ────────────────────────────────────────────────────────────

def _aes_gcm_decrypt(key: bytes, nonce: bytes, ciphertext: bytes, tag: bytes) -> str:
    from Crypto.Cipher import AES
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8")


# ── Chrome 마스터 키 획득 ──────────────────────────────────────────────────────

def _get_chrome_key() -> bytes:
    local_state = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Google", "Chrome", "User Data", "Local State"
    )
    with open(local_state, "r", encoding="utf-8") as f:
        state = json.load(f)

    enc_key = base64.b64decode(state["os_crypt"]["encrypted_key"])
    enc_key = enc_key[5:]  # 앞 "DPAPI" 5바이트 제거
    return _dpapi_decrypt(enc_key)


# ── 쿠키 값 복호화 ────────────────────────────────────────────────────────────

def _decrypt_value(key: bytes, encrypted: bytes) -> str:
    if not encrypted:
        return ""
    try:
        if encrypted[:3] in (b"v10", b"v11"):
            nonce = encrypted[3:15]
            tag = encrypted[-16:]
            ct = encrypted[15:-16]
            return _aes_gcm_decrypt(key, nonce, ct, tag)
        else:
            return _dpapi_decrypt(encrypted).decode("utf-8")
    except Exception:
        return ""


# ── DB 열기 (잠금 우회 3단계) ────────────────────────────────────────────────

def _open_db(path: str):
    import urllib.parse
    import subprocess

    # Windows 절대경로 → SQLite URI (file:///C:/path/to/file)
    fwd = path.replace("\\", "/")
    encoded = urllib.parse.quote(fwd, safe=":/")
    if not encoded.startswith("/"):
        encoded = "/" + encoded

    # 1) immutable 모드: 잠긴 파일 직접 읽기 (쓰기 없음)
    for mode_flag in ("immutable=1", "mode=ro&immutable=1"):
        try:
            uri = f"file://{encoded}?{mode_flag}"
            conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
            conn.execute("SELECT 1 FROM cookies LIMIT 1")
            print("[Chrome 쿠키] immutable 읽기 성공")
            return conn
        except Exception as e:
            print(f"[Chrome 쿠키] immutable({mode_flag}) 실패: {e}")

    # 2) robocopy /B /ZB — 백업 모드 (보안 잠금 우회 + WAL 포함 복사)
    try:
        tmp_dir = tempfile.mkdtemp()
        src_dir = os.path.dirname(path)
        src_file = os.path.basename(path)
        # Cookies-wal, Cookies-shm 도 함께 복사해야 WAL 모드 DB가 온전함
        for extra in [src_file, src_file + "-wal", src_file + "-shm"]:
            subprocess.run(
                ["robocopy", src_dir, tmp_dir, extra, "/B", "/ZB", "/R:1", "/W:0",
                 "/NFL", "/NDL", "/NJH", "/NJS"],
                capture_output=True, timeout=10
            )
        tmp = os.path.join(tmp_dir, src_file)
        if not os.path.exists(tmp):
            raise FileNotFoundError(f"복사된 파일 없음: {tmp}")
        conn = sqlite3.connect(tmp)
        conn.execute("SELECT 1 FROM cookies LIMIT 1")
        print("[Chrome 쿠키] robocopy 복사 성공")
        return conn
    except Exception as e:
        print(f"[Chrome 쿠키] robocopy 실패: {e}")

    return None


# ── 공개 API ─────────────────────────────────────────────────────────────────

def get_chrome_naver_cookies() -> list[dict]:
    """Chrome에서 Naver 쿠키를 추출해 Playwright 형식으로 반환"""
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                        "Google", "Chrome", "User Data", "Default")

    cookies_path = os.path.join(base, "Network", "Cookies")
    if not os.path.exists(cookies_path):
        cookies_path = os.path.join(base, "Cookies")
    if not os.path.exists(cookies_path):
        return []

    try:
        key = _get_chrome_key()
    except Exception as e:
        print(f"[Chrome 쿠키] 마스터 키 획득 실패: {e}")
        return []

    conn = _open_db(cookies_path)
    if conn is None:
        print("[Chrome 쿠키] DB 열기 3가지 방법 모두 실패")
        return []

    cookies = []
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT host_key, name, value, path, expires_utc,
                   is_secure, is_httponly, encrypted_value
            FROM cookies
            WHERE host_key LIKE '%naver.com%'
        """)
        for host, name, value, path, exp, secure, httponly, enc in cur.fetchall():
            if not value and enc:
                value = _decrypt_value(key, enc)
            if not value:
                continue
            expires = (exp / 1_000_000) - 11_644_473_600 if exp > 0 else -1
            cookies.append({
                "name": name,
                "value": value,
                "domain": host,
                "path": path,
                "secure": bool(secure),
                "httpOnly": bool(httponly),
                "expires": int(expires),
            })
        conn.close()
    except Exception as e:
        print(f"[Chrome 쿠키] 읽기 오류: {e}")

    return cookies
