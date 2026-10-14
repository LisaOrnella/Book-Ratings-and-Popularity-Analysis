import os
import json
import logging

import boto3
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename="logs/pipeline.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger().addHandler(console)

S3_BUCKET = os.environ["S3_BUCKET"]
DATABASE_URL = os.environ["DATABASE_URL"]

s3 = boto3.client("s3", region_name=os.environ["AWS_REGION"])

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS books_raw (
    id TEXT PRIMARY KEY,
    subject TEXT,
    payload JSONB NOT NULL,
    loaded_at TIMESTAMP DEFAULT NOW()
);
"""

def get_conn():
    return psycopg2.connect(DATABASE_URL)


def ensure_table(conn):
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLE_SQL)
    conn.commit()
    logging.info("Ensured books_raw table exists")


def list_raw_files():
    """List all JSON files under raw/ in S3."""
    paginator = s3.get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix="raw/"):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".json"):
                keys.append(obj["Key"])
    logging.info(f"Found {len(keys)} raw JSON files in S3")
    return keys


def load_file(conn, key):
    """Download one S3 JSON file and insert its items into books_raw."""
    obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
    items = json.loads(obj["Body"].read())

    # subject is the filename prefix, e.g. raw/fiction_2026-08-04...json -> fiction
    filename = key.split("/")[-1]
    subject = filename.split("_")[0]

    rows = []
    for item in items:
        book_id = item.get("id")
        if not book_id:
            continue
        rows.append((book_id, subject, json.dumps(item)))

    if not rows:
        logging.warning(f"No valid rows found in {key}")
        return 0

    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO books_raw (id, subject, payload)
            VALUES %s
            ON CONFLICT (id) DO NOTHING
            """,
            rows,
            template="(%s, %s, %s::jsonb)"
        )
        inserted = cur.rowcount
    conn.commit()
    logging.info(f"Loaded {key}: {len(rows)} items processed, {inserted} new rows inserted (duplicates skipped)")
    return inserted


def main():
    logging.info("Starting load_raw run")
    conn = get_conn()
    ensure_table(conn)

    keys = list_raw_files()
    total_inserted = 0
    for key in keys:
        total_inserted += load_file(conn, key)

    conn.close()
    logging.info(f"load_raw run complete. Total new rows inserted: {total_inserted}")


if __name__ == "__main__":
    main()