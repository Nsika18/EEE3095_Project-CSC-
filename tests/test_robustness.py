"""Framing and garbage handling (docs/protocol.md section 2): partial, malformed,
oversized and garbage input must give specific NACKs and never corrupt state."""
import time

import pytest

from protocol import EMPTY_BOARD, INCOMPLETE_FRAME_TIMEOUT_S, Kind


def assert_nack(resp, reason):
    assert resp.kind is Kind.NACK and resp.reason == reason, (
        f"expected NACK:{reason}, got {resp.raw!r}"
    )


@pytest.mark.parametrize(
    "frame",
    [
        b"HELLO\n",
        b"move:4\n",          # commands are upper-case only
        b"MOVE\n",
        b"MOVE:\n",
        b"MOVE:abc\n",
        b"MOVE:1.5\n",
        b"MOVE:4:5\n",
        b"NEW:1\n",
        b"\n",
        b"   \n",
    ],
)
def test_malformed_commands_get_badcmd_and_change_nothing(game, frame):
    assert_nack(game.request_raw(frame), "BADCMD")
    assert game.state().board == EMPTY_BOARD


def test_carriage_return_before_newline_is_accepted(game):
    resp = game.request_raw(b"MOVE:4\r\n")
    assert resp.kind is Kind.OK_BOARD and resp.board == "....X....", resp.raw


def test_garbage_bytes_are_rejected_then_normal_traffic_works(game):
    assert_nack(game.request_raw(b"\xff\xfe\x00\x01garbage\x7f\n"), "BADCMD")
    assert game.move(4).board == "....X...."


def test_oversized_frame_is_rejected_then_normal_traffic_works(game):
    assert_nack(game.request_raw(b"A" * 100 + b"\n"), "TOOLONG")
    assert game.move(4).board == "....X...."


def test_oversized_frame_with_valid_prefix_changes_nothing(game):
    assert_nack(game.request_raw(b"MOVE:4" + b"0" * 60 + b"\n"), "TOOLONG")
    assert game.state().board == EMPTY_BOARD


def test_frame_split_across_writes_is_reassembled(game):
    game.write_raw(b"MOV")
    time.sleep(0.05)
    game.write_raw(b"E:")
    time.sleep(0.05)
    resp = game.request_raw(b"4\n")
    assert resp.kind is Kind.OK_BOARD and resp.board == "....X....", resp.raw


def test_stalled_partial_frame_is_discarded_after_timeout(game):
    game.write_raw(b"MOVE:")                       # never finished
    time.sleep(INCOMPLETE_FRAME_TIMEOUT_S + 0.3)   # server drops it
    resp = game.request_raw(b"MOVE:4\n")           # must parse as a fresh frame
    assert resp.kind is Kind.OK_BOARD and resp.board == "....X....", resp.raw


def test_two_frames_in_one_write_get_two_replies(game):
    game.write_raw(b"MOVE:4\nMOVE:0\n")
    first, second = game.read_response(), game.read_response()
    assert first.board == "....X....", first.raw
    assert second.board == "O...X....", second.raw
