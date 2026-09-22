"""Tests for shared job functionality."""

import json

import pytest

from mink.core.jobs import BaseJob

FINAL_PROGRESS = 100
EXPECTED_REAL_SECONDS = 44


@pytest.mark.parametrize(
    "final_record",
    [
        {"level": "FINAL", "message": "Legacy final message"},
        {"event": "final", "message": "Current final message"},
    ],
)
def test_parse_jsonl_output(final_record: dict[str, str]) -> None:
    """Test parsing of JSONL output."""
    # Test if the function supports both the modern and legacy final message formats
    output = "\n".join(
        [
            json.dumps({"level": "PROGRESS", "message": "20%"}),
            json.dumps({"level": "PROGRESS", "message": "100%"}),
            json.dumps(final_record),
            "real 44.72",
            "user 3.76",
            "sys 0.27",
        ]
    )

    parsed_output = BaseJob("test-job", processes=[]).parse_jsonl_output(output)

    assert parsed_output["progress"] == FINAL_PROGRESS
    assert parsed_output["final"] == final_record["message"]
    assert parsed_output["misc"] == []
    assert parsed_output["real_seconds"] == EXPECTED_REAL_SECONDS
