import asyncio

from fastapi import FastAPI

from database import init_db, close_db, DB_PATH, DATABASE_URL


async def main() -> None:
    app = FastAPI()
    await init_db(app)
    active_db = DATABASE_URL if DATABASE_URL else DB_PATH
    print(f"Database initialized at {active_db}")
    await close_db(app)


if __name__ == "__main__":
    asyncio.run(main())
