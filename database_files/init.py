import asyncio

from fastapi import FastAPI

from backend.database import init_db, close_db, DB_PATH


async def main() -> None:
    app = FastAPI()
    await init_db(app)
    print(f"Database initialized at {DB_PATH}")
    await close_db(app)


if __name__ == '__main__':
    asyncio.run(main())
