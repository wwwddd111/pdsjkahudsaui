import asyncio
from pathlib import Path
from bot.storage import Storage


def test_storage_round_trip(tmp_path: Path):
    async def scenario():
        db = Storage(f'sqlite+aiosqlite:///{tmp_path / "test.sqlite3"}')
        await db.init()
        try:
            await db.touch(100, 'tester')
            assert (await db.user(100)).approved is False
            await db.set_flag(100, 'approved', True)
            assert (await db.user(100)).approved is True
            gift = await db.create_card(100, 'Gift #1', 987654321, photo_file_id='test-file-id')
            assert (await db.card(gift.id)).photo_file_id == 'test-file-id'
            assert (await db.card_view(gift.id)).views == 1
            await db.event(100, 'demo_accept')
            stats = await db.stats()
            assert stats['users'] == 1
            assert stats['cards'] == 1
            assert stats['views'] == 1
            assert stats['demo_accepts'] == 1
            await db.set_flag(100, 'banned', True)
            assert (await db.user(100)).banned is True
        finally:
            await db.close()
    asyncio.run(scenario())
