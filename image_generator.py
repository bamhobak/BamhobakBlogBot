import urllib.request
import json
import base64
import io
import time
from PIL import Image
import config

_CF_URL = "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/black-forest-labs/flux-1-schnell"

_warmed_up = False


def _make_request(prompt: str, num_steps: int = 2, seed: int = None) -> urllib.request.Request:
    url = _CF_URL.format(account_id=config.CF_ACCOUNT_ID)
    payload_dict = {
        "prompt": prompt,
        "num_steps": num_steps,
        "width": 512,
        "height": 512,
    }
    if seed is not None:
        payload_dict["seed"] = seed % (2**32)
    payload = json.dumps(payload_dict).encode()
    return urllib.request.Request(url, data=payload, headers={
        "Authorization": f"Bearer {config.CF_API_TOKEN}",
        "Content-Type": "application/json",
    }, method="POST")


def warmup() -> None:
    global _warmed_up
    if not config.CF_ACCOUNT_ID or not config.CF_API_TOKEN:
        raise ValueError("Cloudflare 자격증명이 설정되지 않았습니다.")
    with urllib.request.urlopen(_make_request("test image", num_steps=1, seed=1), timeout=60) as resp:
        resp.read()
    _warmed_up = True


def is_warmed_up() -> bool:
    return _warmed_up


def generate_to_memory(prompt: str, seed: int = 42) -> Image.Image:
    if not config.CF_ACCOUNT_ID or not config.CF_API_TOKEN:
        raise ValueError("설정 탭에서 Cloudflare 자격증명을 먼저 입력해 주세요.")
    last_err = None
    delays = [0, 10, 30]  # 429 rate limit 대비 재시도 간격
    for attempt in range(3):
        if attempt > 0:
            time.sleep(delays[attempt])
        try:
            with urllib.request.urlopen(_make_request(prompt, seed=seed), timeout=120) as resp:
                raw = resp.read()
            try:
                result = json.loads(raw)
                img_data = base64.b64decode(result["result"]["image"])
            except Exception:
                img_data = raw
            img = Image.open(io.BytesIO(img_data))
            img.load()
            return img.copy()
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise ValueError("API 토큰 인증 실패 (401) — 설정 탭에서 Account ID와 API Token을 확인해 주세요.")
            elif e.code == 403:
                raise ValueError("API 권한 없음 (403) — Workers AI 권한이 포함된 토큰인지 확인해 주세요.")
            elif e.code == 429:
                last_err = e
                time.sleep(delays[attempt] + 15)
            else:
                last_err = e
        except Exception as e:
            last_err = e
    raise last_err


def create_placeholder_image() -> Image.Image:
    return Image.new("RGB", (512, 512), color=(70, 130, 180))
