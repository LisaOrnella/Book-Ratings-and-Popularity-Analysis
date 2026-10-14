import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from transform import clean_row, extract_year


def test_clean_row_drops_missing_title():
    """A book with no title should be dropped (returns None)."""
    payload = {"volumeInfo": {}}
    result = clean_row("fake_id_1", payload)
    assert result is None


def test_clean_row_flags_impossible_rating():
    """A rating outside 0-5 should be treated as missing (None), not kept as-is."""
    payload = {
        "volumeInfo": {
            "title": "Test Book",
            "averageRating": 99  # impossible value
        }
    }
    result = clean_row("fake_id_2", payload)
    assert result is not None
    avg_rating = result[7]  # avg_rating is the 8th field in the tuple
    assert avg_rating is None


def test_clean_row_flags_negative_page_count():
    """A negative page count should be treated as missing (None)."""
    payload = {
        "volumeInfo": {
            "title": "Test Book",
            "pageCount": -50  # impossible value
        }
    }
    result = clean_row("fake_id_3", payload)
    page_count = result[4]  # page_count is the 5th field in the tuple
    assert page_count is None


def test_clean_row_keeps_valid_data():
    """A normal, valid book should be kept with all its real values."""
    payload = {
        "volumeInfo": {
            "title": "Valid Book",
            "authors": ["Jane Doe"],
            "publishedDate": "2020-05-01",
            "pageCount": 300,
            "categories": ["Fiction"],
            "language": "en",
            "averageRating": 4.5,
            "ratingsCount": 10
        }
    }
    result = clean_row("fake_id_4", payload)
    assert result is not None
    assert result[1] == "Valid Book"       # title
    assert result[2] == "Jane Doe"         # primary_author
    assert result[3] == 2020               # published_year
    assert result[4] == 300                # page_count
    assert result[7] == 4.5                # avg_rating


def test_extract_year_handles_various_formats():
    """Year extraction should work whether the date is full, partial, or missing."""
    assert extract_year("1999-05-03") == 1999
    assert extract_year("1999-05") == 1999
    assert extract_year("1999") == 1999
    assert extract_year(None) is None
    assert extract_year("") is None