import pandas as pd
from src.dashboard.analytics import to_records

def test_to_records_converts_nan_to_none():
    frame = pd.DataFrame({"a": [1.0, None]})
    rows = to_records(frame)
    assert rows[0]["a"] == 1.0
    assert rows[1]["a"] is None