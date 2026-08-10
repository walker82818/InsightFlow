"""临时诊断：尝试用不同参数连接原生 PostgreSQL。"""
import asyncio
import asyncpg


async def try_connect(dsn, label):
    try:
        conn = await asyncpg.connect(dsn, timeout=5)
        ver = await conn.fetchval("SELECT version()")
        dbs = await conn.fetch("SELECT datname FROM pg_database")
        print(f"[{label}] OK -> {ver}")
        print(f"   dbs: {[r['datname'] for r in dbs]}")
        await conn.close()
    except Exception as e:  # noqa: BLE001
        print(f"[{label}] FAIL -> {type(e).__name__}: {e}")


async def main():
    await try_connect("postgresql://insightflow:insightflow@127.0.0.1:5432/insightflow", "insightflow db")
    await try_connect("postgresql://insightflow:insightflow@127.0.0.1:5432/postgres", "insightflow/postgres")
    await try_connect("postgresql://postgres:postgres@127.0.0.1:5432/postgres", "postgres/postgres")


asyncio.run(main())
