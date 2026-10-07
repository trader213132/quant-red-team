import numpy as np
import pytest

from qrt.realdata import load_real_market


def write(folder, ticker, rows):
    (folder / f"{ticker}.csv").write_text("date,open,close\n" + "".join(f"{d},{o},{c}\n" for d, o, c in rows))


def test_loader_aligns_dates_and_rebuilds_prices(tmp_path):
    write(tmp_path, "AAA", [("2020-01-01", 10, 11), ("2020-01-02", 11.5, 12), ("2020-01-03", 12, 11)])
    write(tmp_path, "BBB", [("2020-01-02", 20, 21), ("2020-01-03", 21, 22), ("2020-01-06", 22, 23)])
    m, dates = load_real_market(tmp_path, ["AAA", "BBB"], "2020-01-01", "2020-12-31")
    assert dates == ["2020-01-02", "2020-01-03"]                       # only days both tickers traded
    assert m.r_on[0].tolist() == [0.0, 0.0]
    assert m.r_id[0] == pytest.approx([12 / 11.5 - 1, 21 / 20 - 1])
    assert m.r_on[1] == pytest.approx([12 / 12 - 1, 21 / 21 - 1])
    assert m.r_id[1] == pytest.approx([11 / 12 - 1, 22 / 21 - 1])
    # the rebuilt close path matches the real one (relative to the first open)
    assert m.close[-1] / m.close[0] == pytest.approx(np.array([11 / 12, 22 / 21]))
    assert m.alive.all()


def test_loader_respects_window(tmp_path):
    write(tmp_path, "AAA", [("2019-12-31", 9, 10), ("2020-01-02", 10, 11), ("2021-01-04", 11, 12)])
    _, dates = load_real_market(tmp_path, ["AAA"], "2020-01-01", "2020-12-31")
    assert dates == ["2020-01-02"]
