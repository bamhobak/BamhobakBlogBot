import os
import re
import sys
import json
import shutil
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

BASE = Path(__file__).parent

def step(n, msg):
    print(f"\n[{n}] {msg}")

def fail(msg):
    print(f"\n[오류] {msg}")
    sys.exit(1)

def remove_files(dist_dir: Path, patterns: list, label: str = ""):
    removed, saved = 0, 0
    for pattern in patterns:
        for f in dist_dir.rglob(pattern):
            if f.is_file():
                saved += f.stat().st_size
                f.unlink()
                removed += 1
    if removed:
        print(f"  {label}: {removed}개 삭제 ({round(saved/1024/1024, 1)} MB)")

def _gh_api(method, url, token, data=None, content_type="application/json"):
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        url, data=body, method=method,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": content_type,
            "User-Agent": "BamhobakBlogBot-Build",
        },
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def create_github_release(token, repo, version, zip_path: Path):
    """GitHub Release 생성 후 zip 업로드. 다운로드 URL 반환."""
    tag = version

    # 기존 릴리즈 삭제 (재빌드 시)
    try:
        existing = _gh_api("GET", f"https://api.github.com/repos/{repo}/releases/tags/{tag}", token)
        _gh_api("DELETE", f"https://api.github.com/repos/{repo}/releases/{existing['id']}", token)
        print(f"  기존 릴리즈 {tag} 삭제")
    except Exception:
        pass

    # 릴리즈 생성
    release = _gh_api("POST", f"https://api.github.com/repos/{repo}/releases", token, {
        "tag_name": tag, "name": f"BamhobakBlogBot {tag}",
        "draft": False, "prerelease": False,
    })
    upload_base = release["upload_url"].split("{")[0]

    # zip 업로드
    zip_bytes = zip_path.read_bytes()
    up_req = urllib.request.Request(
        f"{upload_base}?name={zip_path.name}",
        data=zip_bytes, method="POST",
        headers={
            "Authorization": f"token {token}",
            "Content-Type": "application/zip",
            "User-Agent": "BamhobakBlogBot-Build",
        },
    )
    with urllib.request.urlopen(up_req) as r:
        asset = json.loads(r.read())

    return asset["browser_download_url"]

def update_version_gist(token, gist_id, version, download_url, notes=""):
    """기존 Gist에 version.json 파일 추가/업데이트."""
    payload = {
        "files": {
            "version.json": {
                "content": json.dumps({
                    "version": version,
                    "url": download_url,
                    "notes": notes,
                }, ensure_ascii=False, indent=2)
            }
        }
    }
    _gh_api("PATCH", f"https://api.github.com/gists/{gist_id}", token, payload)

# ── gui.py 에서 상수 추출 ───────────────────────────────────
gui_text = (BASE / "gui.py").read_text(encoding="utf-8")

m = re.search(r'APP_VERSION = "(v[\d.]+)"', gui_text)
VERSION = m.group(1) if m else "v0.0.0"
print(f"빌드 버전: {VERSION}")

m_token = re.search(r'_DEFAULT_GITHUB_TOKEN\s*=\s*"([^"]+)"', gui_text)
m_gist  = re.search(r'_DEFAULT_GIST_URL\s*=\s*"[^"]+/([a-f0-9]{20,})/raw/', gui_text)
m_repo  = re.search(r'_DEFAULT_GITHUB_REPO\s*=\s*"([^"]+)"', gui_text)

GITHUB_TOKEN = m_token.group(1) if m_token else ""
GIST_ID      = m_gist.group(1)  if m_gist  else ""
GITHUB_REPO  = m_repo.group(1)  if m_repo  else "bamhobak/BamhobakBlogBot"

# ── 1. PyInstaller ─────────────────────────────────────────
step(1, "PyInstaller 빌드 중...")
result = subprocess.run(
    [sys.executable, "-m", "PyInstaller", "NaverBlogBot.spec", "--noconfirm"],
    cwd=BASE
)
if result.returncode != 0:
    fail("PyInstaller 빌드 실패")
print("PyInstaller 완료")

dist_dir = BASE / "dist" / "BamhobakBlogBot"

# ── 2. headless shell 복사 ─────────────────────────────────
step(2, "headless shell 복사 중...")
appdata = Path(os.environ.get("LOCALAPPDATA", ""))
ms_playwright = appdata / "ms-playwright"
shell_src = None

if ms_playwright.exists():
    for entry in sorted(ms_playwright.iterdir(), reverse=True):
        if entry.is_dir() and entry.name.startswith("chromium_headless_shell"):
            shell_src = entry
            break

dst_ms = dist_dir / "ms-playwright"
if shell_src:
    dst = dst_ms / shell_src.name
    if dst_ms.exists():
        shutil.rmtree(dst_ms)
    print(f"  원본: {shell_src}")
    print(f"  대상: {dst}")
    shutil.copytree(shell_src, dst)
    print("headless shell 복사 완료")
else:
    print("[경고] headless shell을 찾을 수 없어 생략합니다.")

# ── 3. 불필요한 파일 정리 ──────────────────────────────────
step(3, "불필요한 파일 정리 중...")
remove_files(dist_dir, ["libscipy_openblas64_*.dll"],      "scipy OpenBLAS")
remove_files(dist_dir, ["*.d.ts"],                         "TypeScript 타입 파일")
remove_files(dist_dir, ["LICENSE.headless_shell"],         "라이선스 파일")
remove_files(dist_dir, ["libGLESv2.dll", "libEGL.dll"],    "GL 라이브러리 (headless 불필요)")

# ── 4. ZIP 패키징 ──────────────────────────────────────────
step(4, "ZIP 패키징 중...")
desktop = Path(os.environ.get("USERPROFILE", "~")) / "Desktop"
zip_name = desktop / f"BamhobakBlogBot_{VERSION}.zip"
if zip_name.exists():
    zip_name.unlink()

shutil.make_archive(
    base_name=str(zip_name.with_suffix("")),
    format="zip",
    root_dir=dist_dir,
    base_dir="."
)

size_mb = round(zip_name.stat().st_size / 1024 / 1024, 1)
print(f"ZIP 완료: {zip_name.name} ({size_mb} MB)")

# ── 5. GitHub Release 생성 & 업로드 ───────────────────────
step(5, "GitHub Release 생성 중...")
if not GITHUB_TOKEN:
    print("[건너뜀] GitHub 토큰 없음")
elif not GITHUB_REPO:
    print("[건너뜀] GITHUB_REPO 없음")
else:
    try:
        download_url = create_github_release(GITHUB_TOKEN, GITHUB_REPO, VERSION, zip_name)
        print(f"  릴리즈 업로드 완료")
        print(f"  다운로드 URL: {download_url}")

        # ── 6. Gist version.json 업데이트 ─────────────────
        step(6, "Gist version.json 업데이트 중...")
        if GIST_ID:
            notes = (sys.argv[1] if len(sys.argv) > 1 else "")
            update_version_gist(GITHUB_TOKEN, GIST_ID, VERSION, download_url, notes)
            print(f"  version.json 업데이트 완료 (Gist: {GIST_ID})")
        else:
            print("[건너뜀] Gist ID 없음")

    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        print(f"[오류] GitHub API {e.code}: {body}")
        print("토큰에 repo 권한이 있는지, 저장소가 존재하는지 확인하세요.")
        print(f"저장소: https://github.com/{GITHUB_REPO}")
    except Exception as e:
        print(f"[오류] {e}")

print(f"\n[완료] {zip_name.name}")
