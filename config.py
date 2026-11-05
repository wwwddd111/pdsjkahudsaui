"""Runtime configuration; no credentials in source control."""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def normalize_database_url(url: str) -> str:
    if url.startswith('postgres://'):
        return url.replace('postgres://', 'postgresql+asyncpg://', 1)
    if url.startswith('postgresql://'):
        return url.replace('postgresql://', 'postgresql+asyncpg://', 1)
    if url.startswith('sqlite:///'):
        return url.replace('sqlite:///', 'sqlite+aiosqlite:///', 1)
    return url


@dataclass(frozen=True)
class Settings:
    token: str
    admin_ids: frozenset[int]
    database_url: str

    @classmethod
    def from_env(cls) -> 'Settings':
        token = os.getenv('BOT_TOKEN', '').strip()
        raw = os.getenv('ADMIN_IDS', '').strip()
        if not token:
            raise RuntimeError('BOT_TOKEN is required')
        if not raw:
            raise RuntimeError('ADMIN_IDS is required (comma-separated Telegram IDs)')
        admins = frozenset(int(x.strip()) for x in raw.split(',') if x.strip())
        if not admins:
            raise RuntimeError('ADMIN_IDS must contain at least one ID')
        url = os.getenv('DATABASE_URL', '').strip()
        if not url and os.getenv('RAILWAY_ENVIRONMENT'):
            raise RuntimeError('DATABASE_URL is required on Railway (attach PostgreSQL)')
        return cls(token=token, admin_ids=admins,
                   database_url=normalize_database_url(url or 'sqlite:///demo.sqlite3'))
