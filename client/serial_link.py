"""pyserial wrapper shared by the GUI and the test harness.

GameLink sends one request line, reads one response line and returns it parsed.
It never judges whether a move is legal: that is the server's job.

    link = GameLink("COM5")            # real board
    link = GameLink.simulated()        # built-in simulator, no hardware
    link.open()
    link.connect(); link.new_game(); link.move(4)
"""
from __future__ import annotations

import threading
from time import time
from typing import List, Optional

import serial
from serial.tools import list_ports

from protocol import (
    BAUDRATE,
    CONNECT,
    DISCONNECT,
    NEW,
    RESIGN,
    RESPONSE_TIMEOUT_S,
    STATE,
    TERMINATOR,
    Kind,
    Response,
    move_cmd,
    parse_response,
)


class LinkError(Exception):
    """Serial port could not be opened or failed while in use."""


class LinkTimeout(LinkError):
    """The board did not send a complete line within the timeout."""


def available_ports() -> List[str]:
    """Serial devices currently visible to the OS (COM5, /dev/ttyUSB0, ...)."""
    return [p.device for p in list_ports.comports()]


class GameLink:
    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = BAUDRATE,
        timeout: float = RESPONSE_TIMEOUT_S,
        transport=None,
    ):
        """`transport` lets tests/simulator inject a pyserial look-alike."""
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._ser = transport
        self._lock = threading.RLock()   # one request/response exchange at a time

    # ---------------------------------------------------------- construction
    @classmethod
    def simulated(cls) -> "GameLink":
        """A link wired to the in-process simulator (client/simulator.py)."""
        from simulator import SimulatedSerial

        return cls(port="SIMULATOR", transport=SimulatedSerial())

    # ------------------------------------------------------------- open/close
    @property
    def is_open(self) -> bool:
        return bool(self._ser is not None and getattr(self._ser, "is_open", False))

    def open(self) -> None:
        with self._lock:
            if self.is_open:
                return
            try:
                if self._ser is None:
                    if not self.port:
                        raise LinkError("no serial port selected")
                    self._ser = serial.Serial(
                        self.port,
                        self.baudrate,
                        bytesize=serial.EIGHTBITS,
                        parity=serial.PARITY_NONE,
                        stopbits=serial.STOPBITS_ONE,
                        timeout=self.timeout,
                        write_timeout=self.timeout,
                        xonxoff=False,
                        rtscts=False,
                        dsrdtr=False,
                    )
                else:
                    self._ser.open()
                self._ser.reset_input_buffer()
            except (serial.SerialException, OSError) as exc:
                self._ser = None
                raise LinkError(f"cannot open {self.port}: {exc}") from exc

    def close(self) -> None:
        with self._lock:
            if self._ser is not None:
                try:
                    self._ser.close()
                except (serial.SerialException, OSError):
                    pass

    def __enter__(self) -> "GameLink":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------ raw access
    def write_raw(self, data: bytes) -> None:
        """Write bytes without waiting for a reply (partial frames, pipelining)."""
        with self._lock:
            self._require_open()
            try:
                self._ser.write(data)
                self._ser.flush()
            except (serial.SerialException, OSError) as exc:
                raise LinkError(f"serial write failed: {exc}") from exc

    
    def read_response(self) -> Response:
        """Read response line(s). Handles single lines and multi-line blocks."""
        with self._lock:
            self._require_open()
            try:
                line = self._ser.readline()
            except (serial.SerialException, OSError) as exc:
                raise LinkError(f"serial read failed: {exc}") from exc
                
        if not line:
            raise LinkTimeout("no complete response from the board")
            
        decoded = line.decode("ascii", errors="replace").strip()
        
        # If the simulator or server bundled multiple lines together with \n, 
        # split them so we can evaluate the most important line (like WIN or DRAW)
        lines = [l.strip() for l in decoded.split("\n") if l.strip()]
        
        target_line = lines[-1] if lines else decoded
        for l in lines:
            if l.startswith("WIN:") or l.startswith("DRAW") or l.startswith("OK:BOARD:"):
                target_line = l
                break

        return parse_response(target_line)


    def request_raw(self, data: bytes) -> Response:
        """Send arbitrary bytes and return the one response line (tests use this
        for malformed, oversized and garbage frames)."""
        with self._lock:
            self._require_open()
            try:
                self._ser.reset_input_buffer()   # drop stale bytes from earlier
            except (serial.SerialException, OSError) as exc:
                raise LinkError(f"serial error: {exc}") from exc
            self.write_raw(data)
            return self.read_response()

    def request(self, command: str) -> Response:
        """Send one text command (terminator added) and return the response."""
        return self.request_raw(command.encode("ascii") + TERMINATOR)

    # --------------------------------------------------------- protocol verbs
    def connect(self, recover: bool = False) -> Response:
        """CONNECT. With recover=True, a NACK triggers reset_to_idle() and one
        retry, which clears a session left over from a previous run."""
        resp = self.request(CONNECT)
        if recover and resp.kind is Kind.NACK:
            self.reset_to_idle()
            resp = self.request(CONNECT)
        return resp

    def new_game(self) -> Response:
        return self.request(NEW)

    def move(self, index: int) -> Response:
        return self.request(move_cmd(index))

    def state(self) -> Response:
        return self.request(STATE)

    def resign(self) -> Response:
        return self.request(RESIGN)

    def disconnect(self) -> Response:
        return self.request(DISCONNECT)

    def reset_to_idle(self) -> None:
        """Best effort: RESIGN then DISCONNECT, ignoring the replies. From any
        server state this ends in IDLE (IN_PROGRESS -> GAME_OVER -> IDLE)."""
        for cmd in (RESIGN, DISCONNECT):
            try:
                self.request(cmd)
            except LinkTimeout:
                pass

    # --------------------------------------------------------------- internal
    def _require_open(self) -> None:
        if not self.is_open:
            raise LinkError("serial port is not open")
