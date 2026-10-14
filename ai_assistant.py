import os
import logging
import psycopg2
from groq import Groq
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

client = Groq(api_key=os.environ["GROQ_API_KEY"])
DATABASE_URL = os.environ["DATABASE_URL"]

SCHEMA = """
Table: books_clean
Columns:
  book_id TEXT (unique id)
  title TEXT
  primary_author TEXT
  published_year INTEGER
  page_count INTEGER
  primary_category TEXT (genre, e.g. 'Fiction', 'History', 'Biography & Autobiography'; can be NULL)
  language TEXT (e.g. 'en', 'es', 'fr')
  avg_rating NUMERIC (0-5, NULL if not rated)
  ratings_count INTEGER (NULL if not rated)

Note: when a question asks about a category, genre, author, or year "having" the
highest/lowest/average rating, you must GROUP BY that column and use AVG(avg_rating),
not just filter for the single highest-rated book. Always filter WHERE avg_rating IS NOT NULL
AND the grouping column IS NOT NULL first (e.g. WHERE avg_rating IS NOT NULL AND primary_category IS NOT NULL).
Order by the aggregated value and use LIMIT 1 for "highest"/"lowest" questions.
"""

MODEL_NAME = "llama-3.3-70b-versatile"


import re

def question_to_sql(question):
    """Ask the LLM to turn a plain-English question into a SQL SELECT query."""
    prompt = f"""You are a SQL assistant. Given this PostgreSQL schema:

{SCHEMA}

Write ONE PostgreSQL SELECT query to answer this question. Output ONLY the raw SQL
query and nothing else - no explanation, no markdown code fences, no commentary before
or after. The query must be read-only (SELECT only, never INSERT/UPDATE/DELETE/DROP).
If the question cannot be answered from this schema, output exactly: NO_QUERY

Question: {question}
"""
    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        raw = resp.choices[0].message.content.strip()

        # Extract SQL from a ```sql ... ``` or ``` ... ``` block if present
        code_block = re.search(r"```(?:sql)?\s*(.*?)```", raw, re.DOTALL | re.IGNORECASE)
        if code_block:
            sql = code_block.group(1).strip()
        else:
            # Otherwise, look for a line starting with SELECT
            select_match = re.search(r"(SELECT\s+.*)", raw, re.DOTALL | re.IGNORECASE)
            sql = select_match.group(1).strip() if select_match else raw

        sql = sql.rstrip(";").strip()
        logging.info(f"Question: '{question}' -> SQL: {sql}")
        return sql
    except Exception as e:
        logging.error(f"LLM call failed while generating SQL: {e}")
        return "NO_QUERY"

def is_safe_select(sql):
    """Basic safety check - only allow SELECT statements."""
    lowered = sql.strip().lower()
    if not lowered.startswith("select"):
        return False
    forbidden = ["insert", "update", "delete", "drop", "alter", "truncate", "create"]
    return not any(word in lowered for word in forbidden)


def run_sql(sql):
    """Run the SQL query safely, returning results or an error string."""
    if sql == "NO_QUERY" or not is_safe_select(sql):
        return "ERROR: unsafe or unanswerable query"
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        colnames = [desc[0] for desc in cur.description]
        cur.close()
        conn.close()
        logging.info(f"Query returned {len(rows)} rows")
        return {"columns": colnames, "rows": rows}
    except Exception as e:
        logging.warning(f"SQL execution failed: {e}")
        return f"ERROR: {e}"


def result_to_sentence(question, result):
    """Ask the LLM to turn the SQL result into a plain-English sentence."""
    if isinstance(result, dict):
        columns = result["columns"]
        rows = result["rows"]
        if not rows:
            formatted_result = "No rows were returned - the query found no matching data."
        else:
            formatted_result = f"Columns: {columns}\nRows: {rows}"
    else:
        formatted_result = str(result)

    prompt = f"""Question: {question}
SQL query result:
{formatted_result}

Answer the question in one clear, natural sentence based on this result.
If the rows are empty, say so honestly and suggest the person rephrase.
Do not say the result is empty if rows were actually returned - read the Rows data carefully.
"""
    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"LLM call failed while generating sentence: {e}")
        return "Sorry, I had trouble putting that into words. Please try again."


def ask(question):
    """Full pipeline: question -> SQL -> result -> sentence. Never crashes."""
    sql = question_to_sql(question)
    result = run_sql(sql)

    if isinstance(result, str) and result.startswith("ERROR"):
        logging.warning(f"Could not answer question: '{question}' ({result})")
        return "Sorry, I couldn't find an answer to that in the data. Could you rephrase your question?"

    return result_to_sentence(question, result)


if __name__ == "__main__":
    print("Book Assistant - ask a question about the books dataset (type 'quit' to exit)")
    while True:
        q = input("\nYou: ").strip()
        if q.lower() in ("quit", "exit"):
            break
        if not q:
            continue
        answer = ask(q)
        print(f"Assistant: {answer}")