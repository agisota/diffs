from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
import unicodedata
from pathlib import Path
from typing import Any


def now_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_id(*parts: str, n: int = 16) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:n]


def safe_name(name: str) -> str:
    name = unicodedata.normalize("NFKD", name)
    name = re.sub(r"[^\w.\-а-яА-ЯёЁ]+", "_", name, flags=re.UNICODE)
    name = re.sub(r"_+", "_", name).strip("._")
    return name or "file"


def norm_text(s: str) -> str:
    s = (s or "").replace("ё", "е").replace("Ё", "Е")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[\u00A0\u200B\uFEFF]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def compact_text(s: str, limit: int = 500) -> str:
    s = " ".join((s or "").split())
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def run_cmd(cmd: list[str], timeout: int = 300) -> tuple[int, str, str]:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def has_binary(name: str) -> bool:
    return shutil.which(name) is not None
