"""Required cases from the brief: session, legal move, NACKs, game-over handling."""
import pytest

from protocol import EMPTY_BOARD, Kind


def assert_nack(resp, reason):
    assert resp.kind is Kind.NACK, f"expected NACK:{reason}, got {resp.raw!r}"
    assert resp.reason == reason, f"expected NACK:{reason}, got {resp.raw!r}"


# ---------------------------------------------------------------- session ---
def test_connect_returns_ok(link):
    resp = link.connect()
    assert resp.kind is Kind.OK, resp.raw


def test_new_returns_empty_board(connected):
    resp = connected.new_game()
    assert resp.kind is Kind.OK_BOARD, resp.raw
    assert resp.board == EMPTY_BOARD


def test_new_works_without_connect(link):
    # IDLE accepts CONNECT and NEW (brief, "Server state machine")
    resp = link.new_game()
    assert resp.kind is Kind.OK_BOARD and resp.board == EMPTY_BOARD, resp.raw


# ------------------------------------------------------------- legal moves ---
def test_legal_move_changes_board_exactly(game):
    resp = game.move(4)
    assert resp.kind is Kind.OK_BOARD, resp.raw
    assert resp.board == "....X...."      # X moves first, only cell 4 changed
    resp = game.move(0)
    assert resp.board == "O...X...."      # then O


def test_state_returns_last_confirmed_board(game):
    game.move(4)
    resp = game.state()
    assert resp.kind is Kind.BOARD, resp.raw
    assert resp.board == "....X...."


# ------------------------------------------------------------- rejections ---
def test_occupied_cell_is_rejected_and_board_unchanged(game):
    game.move(4)
    before = game.state().board
    assert_nack(game.move(4), "OCCUPIED")
    assert game.state().board == before


@pytest.mark.parametrize("cell", [-1, 9, 10, 99, 99999999999])
def test_out_of_range_move_is_rejected(game, cell):
    assert_nack(game.move(cell), "RANGE")
    assert game.state().board == EMPTY_BOARD


def test_turn_does_not_advance_after_rejection(game):
    game.move(4)                       # X
    assert_nack(game.move(4), "OCCUPIED")
    assert game.move(0).board == "O...X...."   # still O's turn, so O gets cell 0


# -------------------------------------------------- state-dependent errors ---
def test_move_before_any_game_is_rejected(connected):
    assert_nack(connected.move(4), "NOGAME")


def test_state_before_any_game_is_rejected(connected):
    assert_nack(connected.state(), "NOGAME")
    

def test_move_after_game_over_is_rejected(game):
    game.move(4)
    game.resign()
    assert_nack(game.move(0), "NOGAME")      # brief: NOGAME or documented equivalent
    assert game.state().board == "....X...."  # STATE still works in GAME_OVER


def test_new_after_game_over_starts_a_clean_game(game):
    game.move(4)
    game.resign()
    resp = game.new_game()
    assert resp.kind is Kind.OK_BOARD and resp.board == EMPTY_BOARD, resp.raw
    assert game.move(0).board == "X........"   # X moves first again


def test_new_during_a_game_is_rejected_and_game_continues(game):
    game.move(4)
    assert_nack(game.new_game(), "BADSTATE")
    assert game.state().board == "....X...."


def test_disconnect_after_game_over(game):
    game.resign()
    resp = game.disconnect()
    assert resp.kind is Kind.OK, resp.raw
    assert_nack(game.state(), "NOGAME")       # back in IDLE
