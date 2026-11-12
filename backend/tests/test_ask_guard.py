import pytest

from munim.ask.guard import GuardError, check_sql

ALLOWED = [
    "SELECT sum(amount) AS spent FROM v_expenses WHERE subcategory = 'coffee'",
    "select sum(amount) from V_EXPENSES;",
    "SELECT month, sum(amount) FROM v_entries WHERE kind = 'income' GROUP BY month ORDER BY month",
    "WITH x AS (SELECT * FROM v_expenses WHERE txn_date >= '2026-01-01') SELECT count(*) AS n FROM x",
    "SELECT category FROM v_expenses UNION SELECT category FROM v_entries",
    "SELECT * FROM (SELECT merchant, sum(amount) t FROM v_expenses GROUP BY merchant) ORDER BY t DESC LIMIT 5",
    "SELECT avg(m) FROM (SELECT sum(amount) m FROM v_expenses GROUP BY month)",
]

REJECTED = [
    ("", "empty"),
    ("  ;  ", "empty"),
    ("SELECT * FROM transactions", "Unknown table"),
    ("SELECT * FROM main.transactions", "Schema-qualified"),
    ("SELECT * FROM sqlite_master", "Unknown table"),
    ("SELECT * FROM pragma_table_info('transactions')", "Table functions"),
    ("SELECT * FROM v_expenses; SELECT * FROM v_entries", "Exactly one"),
    ("DROP TABLE transactions", "Only SELECT"),
    ("DELETE FROM v_expenses", "Only SELECT"),
    ("UPDATE v_expenses SET amount = 0", "Only SELECT"),
    ("INSERT INTO imports (filename) VALUES ('x')", "Only SELECT"),
    ("PRAGMA table_info(transactions)", "Only SELECT"),
    ("ATTACH DATABASE 'x.db' AS x", "Only SELECT"),
    ("WITH x AS (SELECT 1) DELETE FROM v_entries", "Only SELECT"),
    ("WITH v_expenses AS (SELECT * FROM transactions) SELECT * FROM v_expenses", "Unknown table"),
    ("SELECT * FROM v_expenses WHERE", "could not be parsed"),
]


@pytest.mark.parametrize("sql", ALLOWED)
def test_allowed(sql):
    assert check_sql(sql)


def test_trailing_semicolon_is_removed():
    assert check_sql("SELECT 1 FROM v_expenses;") == "SELECT 1 FROM v_expenses"


@pytest.mark.parametrize("sql,reason", REJECTED)
def test_rejected(sql, reason):
    with pytest.raises(GuardError) as err:
        check_sql(sql)
    assert reason.lower() in str(err.value).lower()
