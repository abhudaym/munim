import pytest

from munim.importer.normalise import clean_category, content_hash, derive_kind, split_note


def test_category_emoji_is_stripped():
    assert clean_category("Food 🍕") == "Food"
    assert clean_category("Electronics & Games 💻") == "Electronics & Games"
    assert clean_category("Social Life 🪩") == "Social Life"
    assert clean_category("Garage") == "Garage"


def test_category_made_only_of_emoji_falls_back_to_raw():
    assert clean_category("🍕") == "🍕"


def test_note_prefix_becomes_subcategory():
    assert split_note("Coffee: blue tokai") == ("coffee", "blue tokai")
    assert split_note("Eatout: Paul's") == ("eatout", "paul's")


def test_note_without_prefix_is_all_merchant():
    assert split_note("Petrol") == (None, "petrol")
    assert split_note("Ananya Bday gift") == (None, "ananya bday gift")


def test_empty_note():
    assert split_note(None) == (None, None)
    assert split_note("   ") == (None, None)


def test_long_sentence_with_colon_is_not_split():
    note = "Reminder to self about the thing we discussed: call them"
    assert split_note(note) == (None, note.lower())


def test_hash_ignores_nothing_that_can_be_edited():
    base = content_hash(100.0, "Food", "expense", "Coffee: a", None)
    assert base == content_hash(100.0, "Food", "expense", "Coffee: a", None)
    assert base != content_hash(101.0, "Food", "expense", "Coffee: a", None)
    assert base != content_hash(100.0, "Shopping", "expense", "Coffee: a", None)
    assert base != content_hash(100.0, "Food", "expense", "Coffee: b", None)
    assert base != content_hash(100.0, "Food", "income", "Coffee: a", None)
    assert base != content_hash(100.0, "Food", "expense", "Coffee: a", "note")


def test_kind_follows_override_else_direction():
    assert derive_kind("expense", "transfer") == "transfer"
    assert derive_kind("income", None) == "income"
    assert derive_kind("expense", None) == "expense"


# ---------------------------------------------------------------- older entries kept the text in Description

from munim.importer.normalise import promote_description  # noqa: E402


@pytest.mark.parametrize(
    "note,description,expected",
    [
        (None, "Petrol", ("Petrol", None)),
        ("", "Tw coffee ", ("Tw coffee ", None)),
        ("Haircut", "Haircut", ("Haircut", None)),
        ("Haircut", " haircut ", ("Haircut", None)),
        ("Petrol", "Xp95\n15983 kms", ("Petrol", "Xp95\n15983 kms")),
        ("Uber dues", "Airport due for del to blr", ("Uber dues", "Airport due for del to blr")),
        ("Coffee: blue tokai", None, ("Coffee: blue tokai", None)),
        (None, None, (None, None)),
    ],
)
def test_promote_description(note, description, expected):
    assert promote_description(note, description) == expected
