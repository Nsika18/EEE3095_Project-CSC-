"""Client-side definition of the serial game protocol (see docs/protocol.md).

Pure Python, no I/O: the GUI, the serial link, the simulator and the pytest
harness all import the wire-format details from here, so there is one place to
change if the spec changes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

# --- link and framing parameters (docs/protocol.md, sections 1-2) ------------
BAUDRATE = 115200
TERMINATOR = b"\r\n"
MAX_FRAME = 32                       # bytes, including the terminator
INCOMPLETE_FRAME_TIMEOUT_S = 0.5     # server discards a stalled partial frame
RESPONSE_TIMEOUT_S = 1.0             # how long the client waits for a reply

# --- board encoding (section 3) -----------------------------------------------
EMPTY, X, O = ".", "X", "O"
EMPTY_BOARD = EMPTY * 9

# --- commands (section 5) -----------------------------------------------------
CONNECT = "CONNECT"
NEW = "NEW"
STATE = "STATE"
RESIGN = "RESIGN"
DISCONNECT = "DISCONNECT"


def move_cmd(index: int) -> str:
    """Build a MOVE request. No range check here: the server is the referee."""
    return f"MOVE:{index}"


# --- responses (sections 5-6) -------------------------------------------------
class Kind(Enum):
    OK = "OK"                # CONNECT / DISCONNECT accepted
    OK_BOARD = "OK_BOARD"    # NEW or accepted MOVE: OK:BOARD:<9>
    BOARD = "BOARD"          # STATE: BOARD:<9>
    GAMEOVER = "GAMEOVER"    # RESIGN accepted: OK:GAMEOVER
    WIN = "WIN"              # WIN:X / WIN:O (optionally followed by :BOARD:<9>)
    DRAW = "DRAW"            # DRAW (optionally followed by :BOARD:<9>)
    NACK = "NACK"            # NACK:<REASON>
    INVALID = "INVALID"      # anything that is not in the protocol


@dataclass(frozen=True)
class Response:
    kind: Kind
    raw: str
    board: Optional[str] = None      # set for OK_BOARD, BOARD, and WIN/DRAW if sent
    winner: Optional[str] = None     # set for WIN
    reason: Optional[str] = None     # set for NACK

    @property
    def is_nack(self) -> bool:
        return self.kind is Kind.NACK

    @property
    def is_terminal(self) -> bool:
        return self.kind in (Kind.WIN, Kind.DRAW)


_B = r"[.XO]{9}"
_RE_OK_BOARD = re.compile(rf"OK:BOARD:({_B})")
_RE_BOARD = re.compile(rf"BOARD:({_B})")
_RE_WIN = re.compile(rf"WIN:([XO])(?::BOARD:({_B}))?")
_RE_DRAW = re.compile(rf"DRAW(?::BOARD:({_B}))?")
_RE_NACK = re.compile(r"NACK:([A-Z]+)")


def parse_response(line: str) -> Response:
    """Turn one received line into a Response. Never raises."""
    text = line.strip()
    if text == "OK":
        return Response(Kind.OK, text)
    if text == "OK:GAMEOVER":
        return Response(Kind.GAMEOVER, text)
    if m := _RE_OK_BOARD.fullmatch(text):
        return Response(Kind.OK_BOARD, text, board=m.group(1))
    if m := _RE_BOARD.fullmatch(text):
        return Response(Kind.BOARD, text, board=m.group(1))
    if m := _RE_WIN.fullmatch(text):
        return Response(Kind.WIN, text, winner=m.group(1), board=m.group(2))
    if m := _RE_DRAW.fullmatch(text):
        return Response(Kind.DRAW, text, board=m.group(1))
    if m := _RE_NACK.fullmatch(text):
        return Response(Kind.NACK, text, reason=m.group(1))
    return Response(Kind.INVALID, text)


def next_player(board: str) -> str:
    """Whose turn it is, derived from a server-confirmed board (display only)."""
    return X if board.count(X) == board.count(O) else O


NACK_MESSAGES = {
    "OCCUPIED": "That cell is already taken.",
    "RANGE": "That cell does not exist (valid cells are 0 to 8).",
    "NOTURN": "It is not your turn.",
    "NOGAME": "No game is in progress. Press New Game.",
    "BADSTATE": "The board cannot do that in its current state.",
    "BADCMD": "The board did not understand the command.",
    "TOOLONG": "The command was too long for the board.",
}


def describe_nack(reason: Optional[str]) -> str:
    """Human-readable text for a NACK reason (falls back to the raw code)."""
    if reason in NACK_MESSAGES:
        return NACK_MESSAGES[reason]
    return f"Move rejected by the board ({reason})."
