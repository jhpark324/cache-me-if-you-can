from __future__ import annotations

import json
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_path

from second_brain.brand import DEFAULT_PORT


PORT_ERROR = 'SECOND_BRAIN_PORT must be an integer between 1 and 65535.'


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
    port: int = DEFAULT_PORT
    frontend_dir: Path | None = None
    background_jobs: bool = True

    def __post_init__(self):
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError(PORT_ERROR)

    @classmethod
    def load(cls, *, data_dir: Path | None = None, port: int | None = None):
        data = data_dir if data_dir is not None else Path(os.environ.get(
            'SECOND_BRAIN_DATA_DIR', str(user_data_path('SecondBrain', appauthor=False))))
        frontend = Path(__file__).resolve().parents[3] / 'frontend' / 'dist'
        if port is None:
            environment_port = os.environ.get('SECOND_BRAIN_PORT', str(DEFAULT_PORT)).strip()
            if not re.fullmatch(r'[0-9]+', environment_port):
                raise ValueError(PORT_ERROR)
            try:
                port = int(environment_port)
            except ValueError:
                raise ValueError(PORT_ERROR) from None
        return cls(data, port, frontend)

    @property
    def origin(self):
        return f'http://127.0.0.1:{self.port}'

    def initialize(self):
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.data_dir / 'local-access.json'
        if not path.exists():
            atomic_private_json(path, {'mcp_token': secrets.token_urlsafe(48)})
        return json.loads(path.read_text())
