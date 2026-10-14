import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "ingestion", ROOT / "scripts"):
    sys.path.insert(0, str(p))

# modules read these at import time; tests never reach the network
os.environ.setdefault("AWS_BUCKET_NAME", "test-bucket")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("FRED_API_KEY", "test")
