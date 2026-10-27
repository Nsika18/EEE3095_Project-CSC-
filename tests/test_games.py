"""Scripted full games: every winning line for both players, and a draw."""
import itertools

import pytest

from protocol import EMPTY_BOARD, Kind

LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),     # rows
    (0, 3, 6), (1, 4, 7), (2, 5, 8),     # columns
    (0, 4, 8), (2, 4, 6),                # diagonals
]
LINE_IDS = ["-".join(map(str, line)) for line in LINES]

# X O X / X O O / O X X : no line for either player
DRAW_MOVES = [0, 1, 2, 4, 3, 5, 7, 6, 8]
DRAW_BOARD = "XOXXOOOXX"


def x_wins_on(line):
    """X takes `line`; O plays two harmless cells. X wins on its 3rd move."""
    others = [c for c in range(9) if c not in line]
    return [line[0], others[0], line[1], others[1], line[2]]


def o_wins_on(line):
    """X plays three cells that are not a line; O completes `line` on its 3rd move."""
    others = [c for c in range(9) if c not in line]
    x_cells = next(
        trio for trio in itertools.combinations(others, 3)
        if set(trio) not in map(set, LINES)
    )
    return [x_cells[0], line[0], x_cells[1], line[1], x_cells[2], line[2]]


def play(link, moves):
    return [link.move(m) for m in moves]


def assert_all_accepted(responses):
    for r in responses:
        assert r.kind is Kind.OK_BOARD, f"unexpected reply during play: {r.raw!r}"


@pytest.mark.parametrize("line", LINES, ids=LINE_IDS)
def test_x_wins_on_every_line(game, line):
    moves = x_wins_on(line)
    assert_all_accepted(play(game, moves[:-1]))
    final = game.move(moves[-1])
    assert final.kind is Kind.WIN and final.winner == "X", final.raw
    board = game.state().board
    assert all(board[c] == "X" for c in line)


@pytest.mark.parametrize("line", LINES, ids=LINE_IDS)
def test_o_wins_on_every_line(game, line):
    moves = o_wins_on(line)
    assert_all_accepted(play(game, moves[:-1]))
    final = game.move(moves[-1])
    assert final.kind is Kind.WIN and final.winner == "O", final.raw
    board = game.state().board
    assert all(board[c] == "O" for c in line)


def test_draw_is_reported(game):
    assert_all_accepted(play(game, DRAW_MOVES[:-1]))
    final = game.move(DRAW_MOVES[-1])
    assert final.kind is Kind.DRAW, final.raw
    assert game.state().board == DRAW_BOARD


def test_no_moves_accepted_after_a_win(game):
    moves = x_wins_on(LINES[0])
    play(game, moves)
    before = game.state().board
    empty_cell = before.index(".")
    resp = game.move(empty_cell)
    assert resp.kind is Kind.NACK and resp.reason == "NOGAME", resp.raw
    assert game.state().board == before


def test_new_game_after_a_win_starts_clean(game):
    play(game, x_wins_on(LINES[0]))
    resp = game.new_game()
    assert resp.kind is Kind.OK_BOARD and resp.board == EMPTY_BOARD, resp.raw
    assert game.move(8).board == "........X"


@pytest.mark.skip(reason="AI opponent is an optional stretch feature, not implemented yet")
def test_ai_never_plays_an_illegal_move(game):
    """When an AI is added: play full games and assert every server reply is
    OK:BOARD / WIN / DRAW, never a NACK, and the AI never overwrites a cell."""
