from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_path


def atomic_private_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + '.' + secrets.token_hex(8) + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass
class Settings:
    data_dir: Path
    port: int = 8000
    frontend_dir: Path | None = None
    background_jobs: bool = True

    @classmethod
    def load(cls):
        data = Path(os.environ.get('SECOND_BRAIN_DATA_DIR', str(user_data_path('SecondBrain', appauthor=False))))
        frontend = Path(__file__).resolve().parents[3] / 'frontend' / 'dist'
        return cls(data, int(os.environ.get('SECOND_BRAIN_PORT', '8000')), frontend)

    @property
    def origin(self):
        return f'http://127.0.0.1:{self.port}'

    def initialize(self):
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.data_dir / 'local-access.json'
        if not path.exists():
            atomic_private_json(path, {'mcp_token': secrets.token_urlsafe(48)})
        return json.loads(path.read_text())
