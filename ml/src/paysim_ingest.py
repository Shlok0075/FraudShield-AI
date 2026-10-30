"""
FraudShield AI - bulk PaySim ingestion into the backend SQLite database
=====================================================================
Loads the raw PaySim CSV (6,362,620 rows) into the `transactions` table that
the FastAPI backend already serves, plus a sidecar `paysim_labels` table that
carries the ground-truth `isFraud` flag.

    cd ml/src
    python paysim_ingest.py --sample 100k          # validation run
    python paysim_ingest.py                        # full 6.36M row ingest

Why the sidecar table: the dashboard KPIs aggregate `fraud_predictions.risk_level`,
which holds *model output*. PaySim's `isFraud` is *ground truth*, not a prediction.
Writing ground truth into `fraud_predictions` would make a 0% model look like it
scored 6.36M rows. So labels land in `paysim_labels` and the dashboard reports them
as a separate, explicitly-labelled ground-truth series.

Design notes:
  * Streaming `csv.reader`, never `pandas.read_csv` -- peak RSS stays flat regardless
    of file size (the raw CSV is ~471 MB / 6.36M rows).
  * `nameOrig`/`nameDest` are strings like `C1231006815`. `transactions.user_id` is a
    plain indexed INTEGER, so we decode the 10-digit PaySim number to int and offset
    the `M` (merchant) namespace by 2e9 to keep the two namespaces disjoint. Lossless,
    deterministic, and needs no 6.35M-entry dict.
  * `step` is an hour offset with only 743 distinct values, so the timestamp string is
    memoised per step instead of calling strftime 6.36M times.
  * Indexes are dropped for the load and rebuilt after; SQLite is far faster that way.
  * Precomputed rollups (`paysim_rollup_hourly`, `paysim_rollup_type`,
    `paysim_ingest_meta`) are written at the end of the load. Any live aggregate over
    6.36M rows costs 8-10s in SQLite (and COUNT(DISTINCT name_orig) costs 262s), so
    the dashboard reads these instead. Re-run with --refresh-rollups after any change.
"""
from __future__ import annotations

import argparse
import csv
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Keep identical to fraudpipe.datasets.PAYSIM_EPOCH (2024-01-01 00:00 UTC) so the
# ingested `created_at` lines up with the ML pipeline's `ts` column.
PAYSIM_EPOCH = 1_704_067_200
MERCHANT_ID_OFFSET = 2_000_000_000

# Sidecar table holding PaySim ground truth. Additive: created only in the target DB,
# so the existing app database keeps working untouched.
LABELS_DDL = """
CREATE TABLE IF NOT EXISTS paysim_labels (
    id             INTEGER NOT NULL,
    transaction_id INTEGER NOT NULL,
    name_orig      VARCHAR(20) NOT NULL,
    name_dest      VARCHAR(20) NOT NULL,
    txn_type       VARCHAR(20) NOT NULL,
    step           INTEGER NOT NULL,
    amount         NUMERIC(12, 2) NOT NULL,
    is_fraud       INTEGER NOT NULL,
    PRIMARY KEY (transaction_id)
)
"""

# Precomputed rollups. Any live aggregate over 6.36M rows costs 8-10s in SQLite
# (measured: GROUP BY step 8.4s, GROUP BY txn_type 9.4s, COUNT(DISTINCT name_orig)
# 262s), because SQLite must scan the fact table. The corpus is immutable once
# ingested, so the dashboard reads these small rollup tables instead and stays
# sub-100ms.
ROLLUP_HOURLY_DDL = """
CREATE TABLE IF NOT EXISTS paysim_rollup_hourly (
    step         INTEGER NOT NULL,
    transactions INTEGER NOT NULL,
    fraud        INTEGER NOT NULL,
    amount       NUMERIC(20, 2) NOT NULL,
    PRIMARY KEY (step)
)
"""

ROLLUP_TYPE_DDL = """
CREATE TABLE IF NOT EXISTS paysim_rollup_type (
    txn_type     VARCHAR(20) NOT NULL,
    transactions INTEGER NOT NULL,
    fraud        INTEGER NOT NULL,
    amount       NUMERIC(20, 2) NOT NULL,
    fraud_amount NUMERIC(20, 2) NOT NULL,
    PRIMARY KEY (txn_type)
)
"""

META_DDL = """
CREATE TABLE IF NOT EXISTS paysim_ingest_meta (
    key   VARCHAR(64) NOT NULL,
    value TEXT,
    PRIMARY KEY (key)
)
"""

# Prior-transaction count per merchant, including the NULL/"unknown" bucket (key -1).
# The live prediction path needs `counterparty_txn_count_prior`; computing it with a
# SQL COUNT costs ~1.5s here because every bulk row shares merchant_id NULL.
MERCHANT_COUNTS_DDL = """
CREATE TABLE IF NOT EXISTS paysim_merchant_counts (
    merchant_id INTEGER NOT NULL,
    prior_count INTEGER NOT NULL,
    PRIMARY KEY (merchant_id)
)
"""
UNKNOWN_MERCHANT_KEY = -1

DEFAULT_INPUT = Path("../data/raw/PS_20174392719_1491204439457_log.csv")
DEFAULT_DB = Path("../../backend/fraudshield_paysim.db")
DEFAULT_TEMPLATE = Path("../../backend/fraudshield.db")

REQUIRED_COLS = {"step", "type", "amount", "nameOrig", "nameDest", "isFraud"}


def resolve(path: Path) -> Path:
    """Resolve relative to this file so the script works from any cwd."""
    return path if path.is_absolute() else (Path(__file__).resolve().parent / path).resolve()


def parse_count(text: str | None) -> int | None:
    """'100k' -> 100000, '5m' -> 5000000, '1000' -> 1000, None -> None."""
    if text is None:
        return None
    s = str(text).strip().lower()
    mult = 1
    if s.endswith("k"):
        mult, s = 1_000, s[:-1]
    elif s.endswith("m"):
        mult, s = 1_000_000, s[:-1]
    return int(s) * mult


def decode_id(name: str) -> int:
    """`C1231006815` -> 1231006815 ; `M1979787155` -> 1979787155 + 2e9.

    Disjoint namespaces, no collisions, no in-memory mapping table.
    """
    n = int(name[1:])
    return n + MERCHANT_ID_OFFSET if name[0] == "M" else n


def copy_schema(src: sqlite3.Connection, dst: sqlite3.Connection) -> list[str]:
    """Recreate every table/index in `src` on `dst` (schema only, no data)."""
    rows = src.execute(
        "SELECT type, name, sql FROM sqlite_master "
        "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type DESC, name"
    ).fetchall()
    for _kind, name, sql in rows:
        dst.execute(sql)
    return [r[1] for r in rows]


def build_rollups(conn: sqlite3.Connection) -> dict:
    """Recompute the dashboard rollups from `paysim_labels`.

    Idempotent, and usable on its own (`--refresh-rollups`) to pick up new data
    without reloading the fact table. The two COUNT(DISTINCT ...) over text columns
    are the expensive part (~400s at 6.36M rows) but run once, not per request.
    """
    t0 = time.time()
    conn.execute(ROLLUP_HOURLY_DDL)
    conn.execute(ROLLUP_TYPE_DDL)
    conn.execute(META_DDL)
    conn.execute(MERCHANT_COUNTS_DDL)
    for tbl in ("paysim_rollup_hourly", "paysim_rollup_type", "paysim_ingest_meta",
                "paysim_merchant_counts"):
        conn.execute(f"DELETE FROM {tbl}")

    conn.execute("""
        INSERT INTO paysim_rollup_hourly (step, transactions, fraud, amount)
        SELECT step, COUNT(*), COALESCE(SUM(is_fraud), 0), COALESCE(SUM(amount), 0)
        FROM paysim_labels GROUP BY step
    """)
    conn.execute("""
        INSERT INTO paysim_rollup_type (txn_type, transactions, fraud, amount, fraud_amount)
        SELECT txn_type, COUNT(*), COALESCE(SUM(is_fraud), 0), COALESCE(SUM(amount), 0),
               COALESCE(SUM(CASE WHEN is_fraud = 1 THEN amount ELSE 0 END), 0)
        FROM paysim_labels GROUP BY txn_type
    """)

    conn.execute("""
        INSERT INTO paysim_merchant_counts (merchant_id, prior_count)
        SELECT COALESCE(merchant_id, ?), COUNT(*)
        FROM transactions GROUP BY merchant_id
    """, (UNKNOWN_MERCHANT_KEY,))

    meta = {
        "rows": conn.execute("SELECT COUNT(*) FROM paysim_labels").fetchone()[0],
        "fraud": conn.execute("SELECT COALESCE(SUM(is_fraud),0) FROM paysim_labels").fetchone()[0],
        "unique_users": conn.execute("SELECT COUNT(DISTINCT name_orig) FROM paysim_labels").fetchone()[0],
        "unique_counterparties": conn.execute("SELECT COUNT(DISTINCT name_dest) FROM paysim_labels").fetchone()[0],
        "min_step": conn.execute("SELECT MIN(step) FROM paysim_labels").fetchone()[0],
        "max_step": conn.execute("SELECT MAX(step) FROM paysim_labels").fetchone()[0],
        "epoch": str(PAYSIM_EPOCH),
        "id_min": conn.execute("SELECT MIN(id) FROM transactions").fetchone()[0],
        "id_max": conn.execute("SELECT MAX(id) FROM transactions").fetchone()[0],
        "rollups_built_at": datetime.now(timezone.utc).isoformat(),
    }
    conn.executemany("INSERT OR REPLACE INTO paysim_ingest_meta (key, value) VALUES (?, ?)",
                     [(k, str(v)) for k, v in meta.items()])
    conn.commit()
    print(f"[rollup] hourly={conn.execute('SELECT COUNT(*) FROM paysim_rollup_hourly').fetchone()[0]} "
          f"types={conn.execute('SELECT COUNT(*) FROM paysim_rollup_type').fetchone()[0]} "
          f"({time.time()-t0:,.1f}s)")
    return meta


def optimize(conn: sqlite3.Connection, fast: bool) -> None:
    """Bulk-load pragmas: durable enough to be safe, fast enough for 6.36M rows."""
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF" if fast else "PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-131072")   # 128 MB page cache
    conn.execute("PRAGMA temp_store=MEMORY")


def drop_load_indexes(conn: sqlite3.Connection) -> list[str]:
    """Remove the three `transactions` indexes so the load is append-only."""
    dropped = []
    for name in ("ix_transactions_user_id", "ix_transactions_created_at", "ix_transactions_status",
                 "ix_transactions_location", "ix_transactions_payment_method",
                 "ix_transactions_merchant_id"):
        conn.execute(f"DROP INDEX IF EXISTS {name}")
        dropped.append(name)
    return dropped


TXN_INSERT = """
INSERT INTO transactions
    (id, user_id, merchant_id, device_id, amount, currency, location,
     ip_address, payment_method, status, created_at)
VALUES (?, ?, NULL, NULL, ?, 'INR', NULL, NULL, ?, 'completed', ?)
"""
LABEL_INSERT = """
INSERT INTO paysim_labels
    (id, transaction_id, name_orig, name_dest, txn_type, step, amount, is_fraud)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""


def ingest(csv_path: Path, db_path: Path, template_db: Path | None, *,
           limit: int | None = None, batch_size: int = 50_000, fast: bool = True,
           progress_every: int = 500_000, refresh_only: bool = False,
           rebuild: bool = False, id_base: int = 1) -> dict:
    if not csv_path.exists() and not refresh_only:
        raise SystemExit(f"input CSV not found: {csv_path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    fresh = not db_path.exists()

    conn = sqlite3.connect(db_path)
    try:
        optimize(conn, fast)

        if fresh:
            if template_db is None or not template_db.exists():
                raise SystemExit(
                    f"target {db_path.name} does not exist and no template DB was found.\n"
                    "Pass --template-db pointing at a schema-initialised database "
                    "(e.g. backend/fraudshield.db)."
                )
            src = sqlite3.connect(template_db)
            try:
                created = copy_schema(src, conn)
            finally:
                src.close()
            conn.execute(LABELS_DDL)
            conn.commit()
            print(f"[schema] created {len(created)} objects from template {template_db.name}")
        else:
            # Append mode: keep the schema as-is, only add the sidecar if missing.
            conn.execute(LABELS_DDL)
            conn.commit()
            if rebuild:
                # Ids are deterministic (id_base, id_base+1, ...), so an append
                # would collide with the existing rows. Clear the corpus first.
                conn.execute("DELETE FROM fraud_predictions WHERE transaction_id IN "
                             "(SELECT id FROM transactions)")
                conn.execute("DELETE FROM fraud_alerts WHERE transaction_id IN "
                             "(SELECT id FROM transactions)")
                conn.execute("DELETE FROM transactions")
                conn.execute("DELETE FROM paysim_labels")
                conn.commit()
                print(f"[schema] cleared existing corpus in {db_path.name} (--rebuild)")
            print(f"[schema] appending to existing {db_path.name}")

        if refresh_only:
            return {"mode": "refresh-rollups", "meta": build_rollups(conn)}

        dropped = drop_load_indexes(conn)
        conn.commit()
        print(f"[index] dropped {', '.join(dropped)} for bulk load")

        ts_cache: dict[int, str] = {}

        def ts_for(step: int) -> str:
            out = ts_cache.get(step)
            if out is None:
                dt = datetime.fromtimestamp(PAYSIM_EPOCH + step * 3600, tz=timezone.utc).replace(tzinfo=None)
                out = ts_cache[step] = dt.strftime("%Y-%m-%d %H:%M:%S")
            return out

        txn_rows: list[tuple] = []
        label_rows: list[tuple] = []
        stats = {"rows": 0, "fraud": 0, "amount_sum": 0.0, "by_type": {}}
        # The corpus occupies a contiguous, *negative* id range by default so that
        # live transactions created by the app's autoincrement start at 0/1 and
        # never collide with the bulk rows. Everything that references a
        # transaction does so by id, so sign is irrelevant to correctness.
        next_id = id_base
        id_high = next_id
        t0 = time.time()

        with csv_path.open("r", newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            header = next(reader)
            missing = REQUIRED_COLS - set(header)
            if missing:
                raise SystemExit(f"CSV is missing required columns: {sorted(missing)}")
            idx = {name: header.index(name) for name in REQUIRED_COLS}
            i_step, i_type = idx["step"], idx["type"]
            i_amt, i_org = idx["amount"], idx["nameOrig"]
            i_dst, i_fraud = idx["nameDest"], idx["isFraud"]

            for row in reader:
                step = int(row[i_step])
                amt = float(row[i_amt])
                is_fraud = int(row[i_fraud])
                typ = row[i_type]

                txn_rows.append((next_id, decode_id(row[i_org]), round(amt, 2), typ, ts_for(step)))
                label_rows.append((next_id, next_id, row[i_org], row[i_dst], typ, step,
                                   round(amt, 2), is_fraud))

                stats["rows"] += 1
                stats["fraud"] += is_fraud
                stats["amount_sum"] += amt
                t = stats["by_type"].setdefault(typ, [0, 0])
                t[0] += 1
                t[1] += is_fraud
                next_id += 1
                id_high = next_id - 1

                if len(txn_rows) >= batch_size:
                    conn.executemany(TXN_INSERT, txn_rows)
                    conn.executemany(LABEL_INSERT, label_rows)
                    txn_rows.clear()
                    label_rows.clear()
                    if progress_every and stats["rows"] % progress_every < batch_size:
                        el = time.time() - t0
                        print(f"[load] {stats['rows']:,} rows  {stats['rows']/el:,.0f} rows/s",
                              flush=True)

                if limit is not None and stats["rows"] >= limit:
                    break

        if txn_rows:
            conn.executemany(TXN_INSERT, txn_rows)
            conn.executemany(LABEL_INSERT, label_rows)
        conn.commit()

        load_s = time.time() - t0
        print(f"[load] committed {stats['rows']:,} rows in {load_s:,.1f}s "
              f"({stats['rows']/load_s:,.0f} rows/s)", flush=True)

        # Rebuild indexes (much cheaper than maintaining them per-row).
        # `location` is indexed specifically so the dashboard's /geographic GROUP BY
        # runs off an index scan instead of a 6.36M-row table scan.
        t1 = time.time()
        conn.execute("CREATE INDEX IF NOT EXISTS ix_transactions_user_id ON transactions (user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_transactions_created_at ON transactions (created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_transactions_status ON transactions (status)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_transactions_location ON transactions (location)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_transactions_payment_method ON transactions (payment_method)")
        # Serves the live prediction path's counterparty prior-count aggregate.
        conn.execute("CREATE INDEX IF NOT EXISTS ix_transactions_merchant_id ON transactions (merchant_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_paysim_labels_is_fraud ON paysim_labels (is_fraud)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_paysim_labels_type ON paysim_labels (txn_type)")
        conn.execute("ANALYZE")
        conn.commit()
        print(f"[index] rebuilt indexes + ANALYZE in {time.time()-t1:,.1f}s")

        # Rollups are built after the indexes so the GROUP BYs can use them.
        meta = build_rollups(conn)
    finally:
        conn.close()

    rows = stats["rows"]
    db_mb = db_path.stat().st_size / 1024 / 1024
    stats.update({
        "db_path": str(db_path), "db_size_mb": round(db_mb, 1),
        "fraud_rate": round(stats["fraud"] / rows, 6) if rows else 0.0,
        "total_amount": round(stats["amount_sum"], 2),
        "by_type": {k: {"rows": v[0], "fraud": v[1]} for k, v in sorted(stats["by_type"].items())},
        "elapsed_s": round(time.time() - t0, 1),
        "meta": meta,
    })
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="raw PaySim CSV")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="target SQLite file")
    ap.add_argument("--template-db", type=Path, default=DEFAULT_TEMPLATE,
                    help="schema source used when --db does not yet exist")
    ap.add_argument("--sample", type=str, default=None,
                    help="load only the first N rows; accepts a k/m suffix (e.g. --sample 100k)")
    ap.add_argument("--batch-size", type=int, default=50_000)
    ap.add_argument("--safe", action="store_true",
                    help="use synchronous=NORMAL instead of OFF")
    ap.add_argument("--rebuild", action="store_true",
                    help="clear an existing corpus before reloading")
    ap.add_argument("--id-base", type=int, default=-10_000_000,
                    help="first id assigned to the corpus; defaults to -10000000 so the "
                         "corpus sits in a negative id range and live app transactions "
                         "autoincrement from 0/1 (use 0 to opt out)")
    ap.add_argument("--refresh-rollups", action="store_true",
                    help="recompute dashboard rollups from existing data, without reloading")
    a = ap.parse_args(argv)

    limit = parse_count(a.sample)
    if limit == 0:
        limit = None

    template = resolve(a.template_db) if a.template_db else None
    stats = ingest(resolve(a.input), resolve(a.db), template, limit=limit,
                   batch_size=a.batch_size, fast=not a.safe,
                   refresh_only=a.refresh_rollups, rebuild=a.rebuild,
                   id_base=a.id_base)

    if a.refresh_rollups:
        print("\nrollups refreshed:")
        for k, v in stats["meta"].items():
            print(f"  {k:<24} {v}")
        return 0

    print()
    print(f"rows            {stats['rows']:,}")
    print(f"fraud           {stats['fraud']:,}  ({stats['fraud_rate']*100:.4f}%)")
    print(f"total amount    {stats['total_amount']:,.2f}")
    print(f"db size         {stats['db_size_mb']} MB  ({stats['db_path']})")
    print(f"elapsed         {stats['elapsed_s']}s")
    print("\nby txn_type:")
    for k, v in stats["by_type"].items():
        print(f"  {k:<10} {v['rows']:>10,}  fraud {v['fraud']:>7,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
