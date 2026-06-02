import asyncio
from pathlib import Path

from backend.database import connect_db, DB_PATH, DATABASE_URL

async def main() -> None:
    root = Path(__file__).resolve().parent.parent
    seed_path = root / 'database' / 'seeds' / 'dev_seed.sql'
    db = await connect_db()
    try:
        sql = seed_path.read_text(encoding='utf-8')
        await db.executescript(sql)
        await db.commit()
        active_db = DATABASE_URL if DATABASE_URL else DB_PATH
        print(f'Seed data loaded into {active_db}')
    finally:
        await db.close()

if __name__ == '__main__':
    asyncio.run(main())
