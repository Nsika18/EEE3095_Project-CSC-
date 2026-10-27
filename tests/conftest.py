"""Shared fixtures.

By default the tests run against the built-in simulator (client/simulator.py).
To run exactly the same tests against the real STM32 board:

    pytest --port COM5            # Windows
    pytest --port /dev/ttyUSB0    # Linux
    GAME_PORT=COM5 pytest         # or via an environment variable
"""
import os

import pytest

from protocol import EMPTY_BOARD, Kind
from serial_link import GameLink, LinkError


def pytest_addoption(parser):
    parser.addoption(
        "--port",
        default=os.environ.get("GAME_PORT"),
        help="serial port of the STM32 (e.g. COM5, /dev/ttyUSB0); "
        "omit to test the built-in simulator",
    )
    parser.addoption("--baud", type=int, default=115200, help="baud rate (default 115200)")


def pytest_report_header(config):
    port = config.getoption("--port")
    target = f"STM32 on {port}" if port else "built-in simulator (no hardware)"
    return f"game server under test: {target}"


@pytest.fixture
def link(request):
    """An open link with the server reset to IDLE (RESIGN + DISCONNECT)."""
    port = request.config.getoption("--port")
    if port:
        lk = GameLink(port, baudrate=request.config.getoption("--baud"))
    else:
        lk = GameLink.simulated()
    lk.open()
    try:
        lk.reset_to_idle()
        yield lk
    finally:
        try:
            lk.reset_to_idle()      # leave the board IDLE for whoever is next
        except LinkError:
            pass
        lk.close()


@pytest.fixture
def connected(link):
    """Link after a successful CONNECT (server IDLE, session open)."""
    resp = link.connect()
    assert resp.kind is Kind.OK, f"CONNECT failed: {resp.raw!r}"
    return link


@pytest.fixture
def game(connected):
    """Link with a fresh game in progress (empty board, X to move)."""
    resp = connected.new_game()
    assert resp.kind is Kind.OK_BOARD and resp.board == EMPTY_BOARD, (
        f"NEW failed: {resp.raw!r}"
    )
    return connected
