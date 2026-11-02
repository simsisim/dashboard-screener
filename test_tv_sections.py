"""TradingView export with one ###section per industry (leader map tab)."""
import pandas as pd

import dashboard_filters as dfil


def _frame(rows):
    return pd.DataFrame(rows, columns=['ticker', 'group', 'exchange']).set_index('ticker')


def test_groups_together_largest_first_keeping_order():
    f = _frame([('A', 'Software', 'NASDAQ'), ('B', 'Banks', 'NYSE'),
                ('C', 'Software', 'NYSE'), ('D', 'Autos', 'NYSE')])
    assert dfil.tradingview_by_group(f, 'group') == (
        '###Software,NASDAQ:A,NYSE:C,###Autos,NYSE:D,###Banks,NYSE:B\n')


def test_blank_group_last_and_comma_stripped():
    f = _frame([('A', None, 'NYSE'), ('B', 'Oil, gas', 'NYSE')])
    assert dfil.tradingview_by_group(f, 'group') == '###Oil  gas,NYSE:B,###Other,NYSE:A\n'


def test_exchanges_map_used_without_column():
    f = pd.DataFrame({'group': ['Banks']}, index=['B'])
    assert dfil.tradingview_by_group(f, 'group', exchanges={'B': 'NYSE'}) == '###Banks,NYSE:B\n'
