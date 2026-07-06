"""Testy modelu: ekstrakcja rdzenia (§4) i porządek poziomów usługi."""

import pytest

from transport_audit.core.models import ServiceLevel, extract_core


@pytest.mark.parametrize("raw,expected", [
    ("MYBED43503", "43503"),                 # §4/§9 złączenie SPT
    ("Shoper46281-1_8801122", "46281"),      # §4/§9 obetnij _<id>
    ("Shoper43183-1", "43183"),              # łączy się wprost
    ("47559", "47559"),                      # D&M surowy = rdzeń
    ("ZAM/01847", "01847"),
    ("43619 - ODBIOR WLASNY", "43619"),
    ("MYBED ZWROT ID: 600794", "600794"),
    ("ODBIOR WLASNY", None),                 # brak grupy 4-6 cyfr
    ("", None),
    (None, None),
])
def test_extract_core(raw, expected):
    assert extract_core(raw) == expected


def test_service_level_rank_order():
    assert ServiceLevel.DOOR.rank < ServiceLevel.CARRY_IN.rank
    assert ServiceLevel.CARRY_IN.rank < ServiceLevel.CARRY_IN_ASSEMBLY.rank
    assert ServiceLevel.UNKNOWN.rank < ServiceLevel.DOOR.rank
