import os
import re
import logging

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

DATABASE_URL = os.environ["DATABASE_URL"]

CREATE_CLEAN_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS books_clean (
    book_id TEXT PRIMARY KEY,
    title TEXT,
    primary_author TEXT,
    published_year INTEGER,
    page_count INTEGER,
    primary_category TEXT,
    language TEXT,
    avg_rating NUMERIC,
    ratings_count INTEGER
);
"""


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def ensure_table(conn):
    with conn.cursor() as cur:
        cur.execute(CREATE_CLEAN_TABLE_SQL)
    conn.commit()
    logging.info("Ensured books_clean table exists")


def extract_year(published_date):
    """Pull a 4-digit year out of strings like '1999', '1999-05', '1999-05-03'."""
    if not published_date:
        return None
    match = re.match(r"(\d{4})", str(published_date))
    return int(match.group(1)) if match else None


def clean_row(book_id, payload):
    """Turn one raw Google Books JSON record into a clean row tuple, or None if unusable."""
    info = payload.get("volumeInfo", {})

    title = info.get("title")
    authors = info.get("authors") or []
    primary_author = authors[0] if authors else None

    published_year = extract_year(info.get("publishedDate"))

    page_count = info.get("pageCount")
    if page_count is not None and (not isinstance(page_count, int) or page_count <= 0):
        page_count = None  # flag impossible values as missing

    categories = info.get("categories") or []
    primary_category = categories[0] if categories else None

    language = info.get("language")

    avg_rating = info.get("averageRating")
    if avg_rating is not None and not (0 <= avg_rating <= 5):
        avg_rating = None  # impossible rating value

    ratings_count = info.get("ratingsCount")
    if ratings_count is not None and (not isinstance(ratings_count, int) or ratings_count < 0):
        ratings_count = None

    # Require at minimum a title to keep the row
    if not title:
        return None

    return (book_id, title, primary_author, published_year, page_count,
            primary_category, language, avg_rating, ratings_count)


def transform(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT id, payload FROM books_raw;")
        raw_rows = cur.fetchall()
    logging.info(f"Read {len(raw_rows)} rows from books_raw")

    clean_rows = []
    dropped_no_title = 0
    for book_id, payload in raw_rows:
        row = clean_row(book_id, payload)
        if row is None:
            dropped_no_title += 1
            continue
        clean_rows.append(row)

    logging.warning(f"{dropped_no_title} rows dropped - missing title")

    missing_rating = sum(1 for r in clean_rows if r[7] is None)
    missing_pages = sum(1 for r in clean_rows if r[4] is None)
    logging.info(f"{missing_rating} rows missing avg_rating, {missing_pages} rows missing page_count (kept, just null)")

    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE books_clean;")  # rebuild clean table fresh each run - safe since it's fully derived
        execute_values(
            cur,
            """
            INSERT INTO books_clean
            (book_id, title, primary_author, published_year, page_count,
             primary_category, language, avg_rating, ratings_count)
            VALUES %s
            """,
            clean_rows
        )
    conn.commit()
    logging.info(f"Inserted {len(clean_rows)} clean rows into books_clean")


def main():
    logging.info("Starting transform run")
    conn = get_conn()
    ensure_table(conn)
    transform(conn)
    conn.close()
    logging.info("Transform run complete")


if __name__ == "__main__":
    main()