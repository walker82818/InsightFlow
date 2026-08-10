"""临时诊断：用真实已上传数据集验证 DuckDB 注册 + 只读查询 + 守卫。"""
import asyncio
import json

from app.db.session import AsyncSessionLocal
from app.models.dataset import Dataset
from sqlalchemy import select
from app.services import duckdb as d


async def main():
    async with AsyncSessionLocal() as s:
        row = (await s.execute(select(Dataset).order_by(Dataset.created_at.desc()))).scalars().first()
        ds_id = row.id
        sp = row.storage_path
        ft = row.file_type
    print("dataset:", ds_id, "storage_path:", sp, "type:", ft)

    tbl = d.table_name(ds_id)
    d.register_dataset(ds_id, sp, ft)
    print("registered table:", tbl)

    # 1) 聚合查询
    res = d.query(f"SELECT region, SUM(revenue) AS rev FROM {tbl} GROUP BY region ORDER BY rev DESC")
    print("AGG columns:", res["columns"], "row_count:", res["row_count"], "truncated:", res["truncated"])
    for r in res["rows"]:
        print("  ", r)

    # 2) 缺失值过滤
    res2 = d.query(f"SELECT * FROM {tbl} WHERE units IS NULL")
    print("NULL units rows:", res2["row_count"], res2["rows"])

    # 3) 只读守卫：应被拒绝
    for bad in [f"DROP TABLE {tbl}", f"DELETE FROM {tbl}", f"INSERT INTO {tbl} VALUES (1)"]:
        try:
            d.query(bad)
            print("GUARD FAIL for:", bad)
        except d.DuckDBError as e:
            print("GUARD OK rejected:", bad, "->", str(e)[:60])

    # 4) 超时守卫（故意跑慢查询 via a self-join 大数据）
    try:
        d.query(f"SELECT COUNT(*) FROM {tbl} t1, {tbl} t2, {tbl} t3", timeout=1)
        print("timeout not triggered (query too fast)")
    except d.DuckDBError as e:
        print("TIMEOUT guard:", str(e)[:80])


asyncio.run(main())
