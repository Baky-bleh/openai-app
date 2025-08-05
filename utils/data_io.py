import json
from pathlib import Path
from typing import Dict, List
import re

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
JSONL_FILE = DATA_DIR / "records.jsonl"


def append_record(record: Dict) -> None:
    """
    JSONLines 形式で安全に追記する。
    既存ファイルが改行なしで終わっている場合は改行を補う。
    """
    needs_nl = (
        JSONL_FILE.exists()
        and JSONL_FILE.stat().st_size > 0
        and not JSONL_FILE.read_bytes().endswith(b"\n")
    )
    with JSONL_FILE.open("ab") as f:
        if needs_nl:
            f.write(b"\n")
        f.write(json.dumps(record, ensure_ascii=False).encode("utf-8"))
        f.write(b"\n")


def load_records() -> List[Dict]:
    """
    JSONL を安全に読み込む。`}{` で連結された行は分割して救済。
    壊れて読めない行はスキップ。
    """
    if not JSONL_FILE.exists():
        return []

    records: List[Dict] = []
    with JSONL_FILE.open("r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            # 連結 JSON を改行で分割
            parts = re.split(r'}\s*{', raw)
            parts = [parts[0] + "}"] + ["{" + p for p in parts[1:]] if len(parts) > 1 else parts
            for p in parts:
                try:
                    records.append(json.loads(p))
                except json.JSONDecodeError:
                    pass
    return records