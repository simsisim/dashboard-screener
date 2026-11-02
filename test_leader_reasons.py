"""Leader map: the 'why is it a leader' tags under each name in The Plan."""
import numpy as np

from src.leader_map import reasons


def test_tags_in_order():
    r = {'in_minervini': True, 'in_scooter': True, 'in_cantata': True,
         'in_canslim': False, 'rs_pct': 95.0}
    assert reasons(r) == 'Min RS SCTR Cantata'


def test_rs_threshold_and_no_minervini():
    assert reasons({'in_scooter': True, 'rs_pct': 90}) == 'RS SCTR'
    assert reasons({'in_scooter': True, 'rs_pct': 89.9}) == 'SCTR'


def test_outside_universe_is_empty():
    assert reasons({}) == ''
    assert reasons({'in_minervini': np.nan, 'rs_pct': np.nan}) == ''
