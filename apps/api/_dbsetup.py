"""临时诊断：创建 insightflow 角色与数据库（若缺失）。"""
import asyncio
import asyncpg


async def main():
    conn = await asyncpg.connect(
        "postgresql://postgres:postgres@127.0.0.1:5432/postgres", timeout=5
    )
    # 角色
    exists = await conn.fetchval(
        "SELECT 1 FROM pg_roles WHERE rolname='insightflow'"
    )
    if not exists:
        await conn.execute(
            "CREATE ROLE insightflow WITH LOGIN PASSWORD 'insightflow'"
        )
        print("created role insightflow")
    else:
        print("role insightflow already exists")
    # 数据库
    db_exists = await conn.fetchval(
        "SELECT 1 FROM pg_database WHERE datname='insightflow'"
    )
    if not db_exists:
        await conn.execute(
            "CREATE DATABASE insightflow OWNER insightflow"
        )
        print("created database insightflow")
    else:
        print("database insightflow already exists")
    await conn.close()


asyncio.run(main())
