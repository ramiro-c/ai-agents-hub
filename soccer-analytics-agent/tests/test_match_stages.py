"""Tests for FIFA calendar stage migration (parse + apply). No network."""

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from scripts.migrate_match_stages import (
    TEAM_MAP,
    apply_stages,
    parse_fifa_stages,
)

FIXTURE = Path(__file__).parent / "fixtures" / "fifa_calendar_sample.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text())


def test_team_map_covers_fifa_to_kaggle_names():
    assert TEAM_MAP["USA"] == "United States"
    assert TEAM_MAP["Türkiye"] == "Turkey"
    assert TEAM_MAP["Côte d'Ivoire"] == "Ivory Coast"
    assert TEAM_MAP["IR Iran"] == "Iran"
    assert TEAM_MAP["Korea Republic"] == "South Korea"
    assert TEAM_MAP["Congo DR"] == "DR Congo"
    assert TEAM_MAP["Cabo Verde"] == "Cape Verde"
    assert TEAM_MAP["Czechia"] == "Czech Republic"


def test_parse_fifa_stages_maps_sample_rows():
    # parse_fifa_stages returns date objects (YYYY-MM-DD calendar dates).
    payload = _load_fixture()
    rows = parse_fifa_stages(payload)
    by_key = {(h, a): (d, stage) for d, h, a, stage in rows}

    d, stage = by_key[("France", "England")]
    assert d == date(2026, 7, 18)
    assert stage == "Third-place playoff"

    d, stage = by_key[("England", "Argentina")]
    assert d == date(2026, 7, 15)
    assert stage == "Semi-finals"

    d, stage = by_key[("United States", "Paraguay")]
    assert stage == "Group stage"


def test_parse_fifa_stages_rejects_unknown_stage():
    payload = _load_fixture()
    payload["Results"].append(
        {
            "LocalDate": "2026-07-01T12:00:00",
            "StageName": [{"Description": "Banana round"}],
            "Home": {"TeamName": [{"Description": "France"}]},
            "Away": {"TeamName": [{"Description": "Germany"}]},
        }
    )
    with pytest.raises(ValueError):
        parse_fifa_stages(payload)


def test_apply_stages_records_canonical_stage_updates():
    conn = MagicMock()
    rows = [
        (date(2026, 7, 18), "France", "England", "Third-place playoff"),
        (date(2026, 7, 15), "England", "Argentina", "Semi-finals"),
        (date(2026, 6, 11), "United States", "Paraguay", "Group stage"),
    ]
    apply_stages(conn, rows)

    assert conn.execute.call_count == 3
    bound = []
    for call in conn.execute.call_args_list:
        args = call[0]
        if len(args) >= 2:
            bound.append(args[1])
        else:
            bound.append(call[1].get("params") or call[1])

    all_params = []
    for item in bound:
        if isinstance(item, (list, tuple)):
            all_params.extend(item)
        elif item is not None:
            all_params.append(item)

    param_text = " ".join(str(p) for p in all_params)
    assert "Third-place playoff" in param_text
    assert "Semi-finals" in param_text
    assert "Group stage" in param_text
