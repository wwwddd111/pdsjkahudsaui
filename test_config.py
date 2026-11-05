from bot.config import normalize_database_url
from bot.ui import card_text


def test_db_url():
    assert normalize_database_url('postgres://x/y') == 'postgresql+asyncpg://x/y'
    assert normalize_database_url('postgresql://x/y') == 'postgresql+asyncpg://x/y'
    assert normalize_database_url('sqlite:///test.sqlite3') == 'sqlite+aiosqlite:///test.sqlite3'


def test_card_escapes_user_input():
    result = card_text('<script>gift</script>', 12345)
    assert '&lt;script&gt;' in result
    assert 'ДЕМО' in result
    assert '12 345' in result
