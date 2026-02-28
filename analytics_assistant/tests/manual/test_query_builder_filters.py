# -*- coding: utf-8 -*-
"""集成测试：验证 query_builder 日期筛选器去硬编码优化。

运行: cd analytics_assistant && PYTHONPATH=".." python tests/manual/test_query_builder_filters.py
"""

import asyncio, json, logging, os, sys, time
from datetime import date
from typing import Any

_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _root not in sys.path:
    sys.path.insert(0, _root)

logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

pp = lambda o: json.dumps(o, indent=2, ensure_ascii=False, default=str)


def banner(t):
    s = "=" * 70
    print("", s, "  " + t, s, sep="\n")


def make_so(dims, meas, filters=None):
    from analytics_assistant.src.core.schemas.semantic_output import (
        SemanticOutput, WhatClause, WhereClause,
    )
    from analytics_assistant.src.core.schemas import (
        DimensionField, MeasureField, AggregationType, DateGranularity,
    )
    df, mf = [], []
    for d in dims:
        kw = {"field_name": d["f"]}
        if "g" in d:
            kw["date_granularity"] = DateGranularity(d["g"])
        df.append(DimensionField(**kw))
    for m in meas:
        kw = {"field_name": m["f"]}
        if "a" in m:
            kw["aggregation"] = AggregationType(m["a"])
        mf.append(MeasureField(**kw))
    return SemanticOutput(
        what=WhatClause(measures=mf),
        where=WhereClause(dimensions=df, filters=filters or []),
    )


async def run_q(client, ds, key, site, q, label):
    """执行 VizQL 查询并打印结果。"""
    print("  [" + label + "]")
    for i, f in enumerate(q.get("filters", [])):
        ft = f.get("filterType", "?")
        fld = f.get("field", {})
        desc = fld.get("fieldCaption") or fld.get("calculation", "")[:80]
        print(f"    filter[{i}]: {ft} on {desc}")
    t0 = time.time()
    try:
        r = await client.query_datasource(
            datasource_luid=ds, query=q, api_key=key, site=site,
            options={"rowLimit": 20},
        )
        rows = r.get("data", [])
        rc = r.get("rowCount", len(rows))
        print(f"    OK: {rc} rows ({time.time()-t0:.1f}s)")
        if rows:
            print("    Sample: " + json.dumps(rows[0], ensure_ascii=False))
        return r
    except Exception as e:
        print(f"    FAIL ({time.time()-t0:.1f}s): " + str(e)[:200])
        return None


# ── TEST 0: field_samples 数据通路 ──

async def test_0_pipeline(dm):
    banner("TEST 0: field_samples data pipeline")
    samples = getattr(dm, "_field_samples_cache", None) or {}
    print(f"  _field_samples_cache fields: {len(samples)}")
    if samples:
        for n, info in list(samples.items())[:8]:
            print(f"    {n}: {info.get('sample_values', [])[:3]}")
        return True
    print("  !! EMPTY - DATEPARSE will fallback to MATCH !!")
    return False


# ── TEST 1: dt 字段 DATEPARSE ──

async def test_1_dt(adp, dm, cli, key, site, ds):
    banner("TEST 1: dt DATEPARSE RANGE (2024-H1)")
    from analytics_assistant.src.core.schemas import DateRangeFilter
    so = make_so(
        [{"f": "dt", "g": "MONTH"}],
        [{"f": "netamt", "a": "SUM"}],
        [DateRangeFilter(field_name="dt", start_date=date(2024, 1, 1), end_date=date(2024, 6, 30))],
    )
    q = adp.build_query(so, data_model=dm)
    print("  VizQL: " + pp(q))
    r = await run_q(cli, ds, key, site, q, "dt DATEPARSE 2024-H1")
    if r is None:
        return False
    rc = r.get("rowCount", 0)
    if rc <= 1:
        print(f"  !! only {rc} row - format mismatch? !!")
        return False
    print("  PASS")
    return True


# ── TEST 2: yyyymm 字段 DATEPARSE（不再走 SET） ──

async def test_2_yyyymm(adp, dm, cli, key, site, ds):
    banner("TEST 2: yyyymm DATEPARSE RANGE (2024-H1)")
    from analytics_assistant.src.core.schemas import DateRangeFilter
    so = make_so(
        [{"f": "yyyymm"}],
        [{"f": "netamt", "a": "SUM"}],
        [DateRangeFilter(field_name="yyyymm", start_date=date(2024, 1, 1), end_date=date(2024, 6, 30))],
    )
    q = adp.build_query(so, data_model=dm)
    print("  VizQL: " + pp(q))
    fts = q.get("filters", [])
    if fts and fts[0].get("filterType") == "SET":
        print("  !! still SET path - optimization NOT working !!")
        return False
    r = await run_q(cli, ds, key, site, q, "yyyymm 2024-H1")
    if r is None:
        return False
    if r.get("rowCount", 0) <= 1:
        print("  !! too few rows !!")
        return False
    print("  PASS")
    return True


# ── TEST 3: SET + DATEPARSE 组合 ──

async def test_3_combined(adp, dm, cli, key, site, ds):
    banner("TEST 3: SET(guangdong) + DATEPARSE(2024-H2)")
    from analytics_assistant.src.core.schemas import DateRangeFilter, SetFilter
    so = make_so(
        [{"f": "pro_name"}, {"f": "dt", "g": "MONTH"}],
        [{"f": "netamt", "a": "SUM"}],
        [
            SetFilter(field_name="pro_name", values=["广东"]),
            DateRangeFilter(
                field_name="dt",
                start_date=date(2024, 7, 1),
                end_date=date(2024, 12, 31),
            ),
        ],
    )
    q = adp.build_query(so, data_model=dm)
    print("  VizQL: " + pp(q))
    r = await run_q(cli, ds, key, site, q, "guangdong+2024H2")
    if r is None or r.get("rowCount", 0) < 1:
        print("  !! no data !!")
        return False
    print("  PASS")
    return True


# ── TEST 4: MATCH fallback ──

async def test_4_fallback():
    banner("TEST 4: MATCH fallback (no samples)")
    from analytics_assistant.src.core.schemas import DateRangeFilter
    from analytics_assistant.src.platform.tableau.query_builder import TableauQueryBuilder
    b = TableauQueryBuilder()
    f = DateRangeFilter(
        field_name="fake_field",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )
    meta = {"fake_field": {"dataType": "STRING"}}
    r = b._build_date_range_filter(f, meta)
    print("  filter: " + pp(r))
    ok = (
        r is not None
        and r.get("filterType") == "MATCH"
        and r.get("startsWith") == "2024"
    )
    print("  PASS" if ok else "  !! FAIL !!")
    return ok


# ── MAIN ──

async def main():
    from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
    from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
    from analytics_assistant.src.platform.tableau.client import VizQLClient
    from analytics_assistant.src.platform.tableau.adapter import TableauAdapter

    banner("query_builder filter integration test - START")

    print("Authenticating...")
    auth = await get_tableau_auth_async()
    print(f"  site={auth.site}")

    print("Loading data model...")
    t0 = time.time()
    async with TableauDataLoader() as loader:
        dm = await loader.load_data_model(datasource_name="销售", auth=auth)
    ds = dm.datasource_id
    print(f"  ds={ds}, fields={len(dm.fields)}, {time.time()-t0:.1f}s")

    cli = VizQLClient()
    adp = TableauAdapter(vizql_client=cli)
    results = {}

    try:
        results["T0"] = await test_0_pipeline(dm)
        args = (adp, dm, cli, auth.api_key, auth.site, ds)
        results["T1_dt"] = await test_1_dt(*args)
        results["T2_yyyymm"] = await test_2_yyyymm(*args)
        results["T3_combined"] = await test_3_combined(*args)
        results["T4_fallback"] = await test_4_fallback()
    finally:
        await cli.close()

    banner("SUMMARY")
    p = f = 0
    for name, ok in results.items():
        sym = "+" if ok else "X"
        st = "PASS" if ok else "FAIL"
        print(f"  [{sym}] {name}: {st}")
        if ok:
            p += 1
        else:
            f += 1
    print(f"  {p} passed, {f} failed")
    banner("DONE")


if __name__ == "__main__":
    asyncio.run(main())
