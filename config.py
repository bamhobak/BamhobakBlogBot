import os
import sys
from pathlib import Path
from dotenv import load_dotenv

_BASE_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
load_dotenv(_BASE_DIR / ".env")

CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID", "")
CF_API_TOKEN  = os.getenv("CF_API_TOKEN", "")
NAVER_BLOG_ID = os.getenv("NAVER_BLOG_ID", "")
GITHUB_TOKEN  = os.getenv("GITHUB_TOKEN", "")
