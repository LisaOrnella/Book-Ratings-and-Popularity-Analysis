import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ai_assistant import is_safe_select, ask, run_sql


def test_is_safe_select_allows_plain_select():
    assert is_safe_select("SELECT * FROM books_clean") is True


def test_is_safe_select_blocks_delete():
    assert is_safe_select("DELETE FROM books_clean") is False


def test_is_safe_select_blocks_drop():
    assert is_safe_select("DROP TABLE books_clean") is False


def test_is_safe_select_blocks_no_query_marker():
    assert is_safe_select("NO_QUERY") is False


def test_run_sql_rejects_unsafe_query():
    """run_sql should refuse to execute a non-SELECT statement, never touching the DB."""
    result = run_sql("DELETE FROM books_clean")
    assert isinstance(result, str)
    assert result.startswith("ERROR")


@patch("ai_assistant.question_to_sql")
@patch("ai_assistant.run_sql")
@patch("ai_assistant.result_to_sentence")
def test_ask_normal_question_returns_string(mock_sentence, mock_run_sql, mock_to_sql):
    """A normal question should flow through and return a string answer, not crash."""
    mock_to_sql.return_value = "SELECT primary_category FROM books_clean LIMIT 1"
    mock_run_sql.return_value = {"columns": ["primary_category"], "rows": [("Fiction",)]}
    mock_sentence.return_value = "The category is Fiction."

    answer = ask("Which category has the most books?")
    assert isinstance(answer, str)
    assert len(answer) > 0


@patch("ai_assistant.question_to_sql")
@patch("ai_assistant.run_sql")
def test_ask_unanswerable_question_does_not_crash(mock_run_sql, mock_to_sql):
    """A nonsense question should return a graceful message, not raise an exception."""
    mock_to_sql.return_value = "NO_QUERY"
    mock_run_sql.return_value = "ERROR: unsafe or unanswerable query"

    answer = ask("What's the weather like in the story?")
    assert isinstance(answer, str)
    assert "sorry" in answer.lower() or "couldn't" in answer.lower()