from datetime import date

from munim.ask import Draft
from munim.ask.context import date_tokens
from munim.ask.evals import latest_data_date, load_golden, run_eval, same_answer

TODAY = date(2026, 4, 10)


class Oracle:
    """Answers every golden question with its reference query, so all should pass."""

    name = "oracle"

    def __init__(self, wrong=()):
        self.by_q = {g["q"]: g["sql"] for g in load_golden()}
        self.wrong = set(wrong)

    def write_query(self, question, context, previous=None):
        sql = self.by_q[question]
        if question in self.wrong:
            return Draft("SELECT 1", None)
        return Draft(sql.format(**date_tokens(TODAY)) if sql else None, "")


def test_golden_file_is_well_formed():
    golden = load_golden()
    assert len(golden) >= 15 and len({g["q"] for g in golden}) == len(golden)
    assert any(g["sql"] is None for g in golden)  # at least one must-decline case


def test_reference_queries_all_run(db_path):
    rows = run_eval(db_path, Oracle(), today=TODAY)
    assert [r.detail for r in rows if not r.ok] == []


def test_a_wrong_answer_is_flagged(db_path):
    first = load_golden()[0]["q"]
    rows = run_eval(db_path, Oracle(wrong=[first]), today=TODAY, limit=3)
    assert [r.ok for r in rows] == [False, True, True]


def test_defaults_today_to_latest_entry(db_path):
    assert latest_data_date(db_path) == date(2026, 4, 2)


def test_comparison_ignores_order_and_float_noise():
    assert same_answer([["a", 1.001], ["b", 2.0]], [["b", 2.0], ["a", 1.0]])
    assert not same_answer([[1]], [[2]])


def test_comparison_allows_extra_columns_but_not_wrong_values():
    assert same_answer([["petrol", 135868.74]], [["petrol"]])
    assert same_answer([[128386.0, "2026-08"]], [["2026-08"]])
    assert same_answer([["2026-03", 9, 95583.0], ["2026-04", 4, 83135.0]], [["2026-04", 83135.0], ["2026-03", 95583.0]])
    assert not same_answer([["Food", 844620.41]], [[26000.0]])
    assert not same_answer([["petrol"]], [["petrol", 1.0]])
    assert not same_answer([["a"], ["b"]], [["a"]])
    assert same_answer([], [])
