"""In-process stand-in for the STM32 server, so the GUI and the tests can run
without the board.

It implements docs/protocol.md exactly as written. It is NOT the
real referee: the firmware is. Use it to develop the client and to check that
the tests themselves are sane; run `pytest --port <PORT>` for the real thing.

    SimulatedServer  - the game rules and FSM (bytes in, one reply string out)
    SimulatedSerial  - a pyserial look-alike (write/readline/...) around it,
                       including 32-byte frame limit and 500 ms partial-frame
                       timeout, so framing tests mean something
"""
from __future__ import annotations

import re
import time
from typing import Optional

from protocol import INCOMPLETE_FRAME_TIMEOUT_S, MAX_FRAME, RESPONSE_TIMEOUT_S

IDLE, IN_PROGRESS, GAME_OVER = "IDLE", "IN_PROGRESS", "GAME_OVER"

WIN_LINES = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
)

_MOVE_RE = re.compile(r"MOVE:(-?[0-9]+)")


class SimulatedServer:
    def __init__(self) -> None:
        self.state = IDLE
        self.board = ["."] * 9
        self.turn = "X"

    # one complete frame (terminator included) in, one reply line out
    def handle_frame(self, frame: bytes) -> str:
        if len(frame) > MAX_FRAME:
            return "NACK:TOOLONG"
        try:
            text = frame.decode("ascii")
        except UnicodeDecodeError:
            return "NACK:BADCMD"
        text = text.rstrip("\r\n")
        if not text.isprintable():
            return "NACK:BADCMD"

        if text == "CONNECT":
            return "OK" if self.state == IDLE else "NACK:BADSTATE"
        if text == "NEW":
            if self.state in (IDLE, GAME_OVER):
                self.board, self.turn, self.state = ["."] * 9, "X", IN_PROGRESS
                return "OK:BOARD:" + self._board()
            return "NACK:BADSTATE"
        if text == "STATE":
            return "BOARD:" + self._board() if self.state != IDLE else "NACK:NOGAME"
        if text == "RESIGN":
            if self.state == IN_PROGRESS:
                self.state = GAME_OVER
                # Opponent of the current player wins on resignation
                winner = "O" if self.turn == "X" else "X"
                return f"BOARD:{self._board()}\nWIN:{winner}\nOK:GAMEOVER"
            return "NACK:NOGAME"
        if text == "DISCONNECT":
            if self.state == GAME_OVER:
                self.state = IDLE
                return "OK"
            return "NACK:BADSTATE"
        if m := _MOVE_RE.fullmatch(text):
            return self._move(int(m.group(1)))
        return "NACK:BADCMD"

    def _move(self, cell: int) -> str:
        # order: syntax (done) -> state -> range -> occupied -> apply
        if self.state != IN_PROGRESS:
            return "NACK:NOGAME"
        if not 0 <= cell <= 8:
            return "NACK:RANGE"
        if self.board[cell] != ".":
            return "NACK:OCCUPIED"
        self.board[cell] = self.turn

        if any(all(self.board[i] == self.turn for i in line) for line in WIN_LINES):
            self.state = GAME_OVER
            return f"BOARD:{self._board()}\nWIN:{self.turn}\nOK:GAMEOVER"
        
        if "." not in self.board:
            self.state = GAME_OVER
            return f"BOARD:{self._board()}\nDRAW\nOK:GAMEOVER"

        self.turn = "O" if self.turn == "X" else "X"
        return "OK:BOARD:" + self._board()

    def _board(self) -> str:
        return "".join(self.board)


class SimulatedSerial:
    """Just enough of serial.Serial for GameLink."""

    def __init__(self, server: Optional[SimulatedServer] = None,
                 timeout: float = RESPONSE_TIMEOUT_S) -> None:
        self.server = server or SimulatedServer()
        self.timeout = timeout
        self.is_open = True
        self._rx = bytearray()      # partial frame being received
        self._overflow = False      # current frame exceeded MAX_FRAME
        self._last_rx = 0.0
        self._tx = bytearray()      # replies waiting to be read

    def open(self) -> None:
        self.is_open = True

    def close(self) -> None:
        self.is_open = False

    def flush(self) -> None:
        pass

    def reset_input_buffer(self) -> None:
        self._tx.clear()

    @property
    def in_waiting(self) -> int:
        return len(self._tx)

    def write(self, data: bytes) -> int:
        if not self.is_open:
            raise OSError("port is closed")
        now = time.monotonic()
        if self._rx and now - self._last_rx > INCOMPLETE_FRAME_TIMEOUT_S:
            self._rx.clear()            # stalled partial frame is dropped
            self._overflow = False
        for byte in data:
            if byte == 0x0A:
                if self._overflow:
                    reply = "NACK:TOOLONG"
                else:
                    reply = self.server.handle_frame(bytes(self._rx) + b"\n")
                self._tx += reply.encode("ascii") + b"\r\n"
                self._rx.clear()
                self._overflow = False
            elif len(self._rx) >= MAX_FRAME - 1:   # no room left before "\n"
                self._overflow = True
            else:
                self._rx.append(byte)
        self._last_rx = now
        return len(data)

    def readline(self) -> bytes:
        """One reply line, or b'' (a timeout) if nothing is waiting."""
        if not self.is_open:
            raise OSError("port is closed")
        end = self._tx.find(b"\r\n")
        if end < 0:
            return b""
        line = bytes(self._tx[: end + 2])
        del self._tx[: end + 2]
        return line