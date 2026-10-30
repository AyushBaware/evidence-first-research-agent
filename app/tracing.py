import json
import time
import uuid
from datetime import datetime
from pathlib import Path

TRACE_DIR = Path("traces")


class Tracer:
    """Writes one JSON line per event to traces/<run_id>.jsonl"""

    def __init__(self, question: str):
        TRACE_DIR.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.run_id = f"{stamp}-{uuid.uuid4().hex[:6]}"
        self.path = TRACE_DIR / f"{self.run_id}.jsonl"
        self.start = time.time()
        self.log("run_start", question=question)

    def log(self, event: str, **data):
        record = {"t": round(time.time() - self.start, 3), "event": event, **data}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")