import os
import json
import time
import logging
from datetime import datetime, timezone

import boto3
import requests
from dotenv import load_dotenv

load_dotenv()

# --- Logging setup ---
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename="logs/pipeline.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger().addHandler(console)

BASE_URL = "https://www.googleapis.com/books/v1/volumes"
GOOGLE_BOOKS_API_KEY = os.environ.get("GOOGLE_BOOKS_API_KEY", "")

# Genres to pull — expanded for a bigger, more ML-usable dataset
SUBJECTS = ["fiction", "history", "science", "romance", "biography",
            "fantasy", "mystery", "self-help", "poetry", "philosophy",
            "thriller", "young adult", "classics", "business", "cooking",
            "technology", "psychology", "travel", "horror", "sports"]

s3 = boto3.client("s3", region_name=os.environ["AWS_REGION"])
S3_BUCKET = os.environ["S3_BUCKET"]


def fetch_with_retry(params, max_attempts=4):
    if GOOGLE_BOOKS_API_KEY:
        params = {**params, "key": GOOGLE_BOOKS_API_KEY}

    for attempt in range(1, max_attempts + 1):
        try:
            r = requests.get(BASE_URL, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            logging.info(f"Request succeeded on attempt {attempt} - q={params.get('q')} startIndex={params.get('startIndex')}")
            return data
        except requests.RequestException as e:
            logging.warning(f"Attempt {attempt} failed for q={params.get('q')}: {e}")
            time.sleep(2 ** attempt)  # backoff: 2s, 4s, 8s...
    logging.error(f"Giving up after {max_attempts} attempts - q={params.get('q')}")
    return None


def fetch_subject(subject, max_results=40, max_pages=10):
    """Pull up to max_pages * max_results books for one subject/genre."""
    all_items = []
    for page in range(max_pages):
        start = page * max_results
        data = fetch_with_retry({
            "q": f"subject:{subject}",
            "startIndex": start,
            "maxResults": max_results
        })
        if not data or "items" not in data:
            logging.info(f"No more results for '{subject}' at startIndex {start}")
            break
        all_items.extend(data["items"])
        logging.info(f"'{subject}': {len(data['items'])} items at page {page} (total so far: {len(all_items)})")
        time.sleep(1)  # be polite to the API between pages
    return all_items


def save_raw_to_s3(subject, items):
    """Save raw JSON for one subject to S3, timestamped."""
    if not items:
        return None
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    safe_subject = subject.replace(" ", "-")
    key = f"raw/{safe_subject}_{timestamp}.json"
    body = json.dumps(items).encode("utf-8")
    s3.put_object(Bucket=S3_BUCKET, Key=key, Body=body)
    logging.info(f"Saved {len(items)} raw items for '{subject}' to s3://{S3_BUCKET}/{key}")
    return key


def main():
    logging.info("Starting extract run")
    all_results = {}
    for subject in SUBJECTS:
        logging.info(f"Fetching subject: {subject}")
        items = fetch_subject(subject)
        s3_key = save_raw_to_s3(subject, items)
        all_results[subject] = {"count": len(items), "s3_key": s3_key}
        time.sleep(2)  # pause between subjects
    logging.info(f"Extract run complete. Summary: {all_results}")
    return all_results


if __name__ == "__main__":
    main()