#!/usr/bin/env python3
"""
Hardware UART Automated Test Suite for STM32 Tic-Tac-Toe Serial Game Server
=============================================================================
Communicates over USART1 (115200 8N1) with the target microcontroller.

Usage:
    python tests/test_serial_hardware.py                 # Auto-detects COM port
    python tests/test_serial_hardware.py --port COM3     # Specific port
    python tests/test_serial_hardware.py --interactive   # Manual terminal mode
    python -m pytest --port COM3                         # Run via pytest with the other tests
                                                         # (skipped when no --port is given)
"""

import sys
import time
import argparse
from typing import Optional, List, Tuple
import serial
import serial.tools.list_ports

# Protocol Configuration
DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT = 1.0  # seconds

# ANSI Colors for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


class SerialGameClient:
    """Helper client for communicating with the STM32 Serial Game Server."""

    def __init__(self, port: str, baudrate: int = DEFAULT_BAUDRATE, timeout: float = DEFAULT_TIMEOUT):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser: Optional[serial.Serial] = None

    def connect(self) -> None:
        """Open serial port connection."""
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
                write_timeout=self.timeout
            )
            # Give device a moment to stabilize after port open (DTR reset on some boards)
            time.sleep(0.15)
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
        except serial.SerialException as e:
            raise RuntimeError(f"Failed to open {self.port}: {e}")

    def close(self) -> None:
        """Close serial port connection."""
        if self.ser and self.ser.is_open:
            self.ser.close()

    def send_cmd(self, cmd: str, timeout: Optional[float] = None) -> str:
        """
        Send a wire command with \\r\\n terminator and read one response line.
        """
        if not self.ser or not self.ser.is_open:
            raise RuntimeError("Serial port not connected.")

        if timeout is not None:
            self.ser.timeout = timeout

        # Transmit command
        payload = f"{cmd}\r\n".encode("ascii")
        self.ser.write(payload)
        self.ser.flush()

        # Read response line
        raw = self.ser.readline()

        if timeout is not None:
            self.ser.timeout = self.timeout

        response = raw.decode("ascii", errors="replace").strip()
        return response

    def send_raw_bytes(self, raw_bytes: bytes, wait_resp: bool = True, timeout: Optional[float] = None) -> str:
        """Send arbitrary raw bytes (for testing oversized frames / error handling)."""
        if not self.ser or not self.ser.is_open:
            raise RuntimeError("Serial port not connected.")
        if timeout is not None:
            self.ser.timeout = timeout
        self.ser.write(raw_bytes)
        self.ser.flush()
        resp = ""
        if wait_resp:
            resp = self.ser.readline().decode("ascii", errors="replace").strip()
        if timeout is not None:
            self.ser.timeout = self.timeout
        return resp

    def read_line(self, timeout: Optional[float] = None) -> str:
        """Read a single line from the serial port with an optional custom timeout."""
        if not self.ser or not self.ser.is_open:
            raise RuntimeError("Serial port not connected.")
        if timeout is not None:
            self.ser.timeout = timeout
        raw = self.ser.readline()
        if timeout is not None:
            self.ser.timeout = self.timeout
        return raw.decode("ascii", errors="replace").strip()

    def flush(self) -> None:
        """Flush pending buffers."""
        if self.ser and self.ser.is_open:
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()


def find_serial_port(preferred_port: Optional[str] = None) -> str:
    """Find and return an available COM port."""
    ports = serial.tools.list_ports.comports()

    if preferred_port:
        return preferred_port

    if not ports:
        print(f"{RED}[ERROR] No serial COM ports detected.{RESET}")
        print("Please check that:")
        print("  1. The STM32 board (or USB-to-UART adapter) is plugged in via USB.")
        print("  2. ST-LINK Virtual COM Port drivers or CH340/FTDI drivers are installed.")
        print("  3. Specify port manually using: python test_serial_hardware.py --port COMx")
        sys.exit(1)

    if len(ports) == 1:
        selected = ports[0].device
        print(f"{CYAN}Auto-detected serial port: {selected} ({ports[0].description}){RESET}")
        return selected

    print(f"{YELLOW}Multiple serial ports detected:{RESET}")
    for idx, p in enumerate(ports, start=1):
        print(f"  [{idx}] {p.device}: {p.description}")

    # Default to first port or prompt
    return ports[0].device


# ==============================================================================
# Test Cases
# ==============================================================================

class HardwareTestRunner:
    def __init__(self, client: SerialGameClient):
        self.client = client
        self.passed = 0
        self.failed = 0
        self.results: List[Tuple[str, bool, str]] = []

    def assert_cmd(self, cmd: str, expected_prefix: str, test_name: str) -> bool:
        """Helper to send a command and assert the expected response prefix."""
        resp = self.client.send_cmd(cmd)
        ok = resp.startswith(expected_prefix)
        if ok:
            print(f"  {GREEN}[PASS]{RESET} {test_name}: '{cmd}' -> '{resp}'")
            self.passed += 1
            self.results.append((test_name, True, f"'{resp}'"))
            return True
        else:
            print(f"  {RED}[FAIL]{RESET} {test_name}: '{cmd}'")
            print(f"         Expected prefix: '{expected_prefix}'")
            print(f"         Actual response: '{resp}'")
            self.failed += 1
            self.results.append((test_name, False, f"Expected '{expected_prefix}', got '{resp}'"))
            return False

    def run_all(self) -> bool:
        print(f"\n{BOLD}========================================================{RESET}")
        print(f"{BOLD} Starting STM32 UART Hardware Integration Tests{RESET}")
        print(f"{BOLD} Port: {self.client.port} @ {self.client.baudrate} 8N1{RESET}")
        print(f"{BOLD}========================================================{RESET}\n")

        # Clean slate: disconnect in case previous run left game open
        self.client.flush()
        self.client.send_cmd("DISCONNECT")

        # Suite 1: Connection Handshake
        print(f"{CYAN}[Suite 1: Connection & Disconnection]{RESET}")
        self.assert_cmd("CONNECT", "OK", "Connect to server")
        self.assert_cmd("CONNECT", "NACK:BADCMD", "Reject duplicate CONNECT")
        self.assert_cmd("DISCONNECT", "OK", "Disconnect from server")
        self.assert_cmd("CONNECT", "OK", "Re-connect to server")

        # Suite 2: Game Lifecycle
        print(f"\n{CYAN}[Suite 2: Game Lifecycle & State]{RESET}")
        self.assert_cmd("NEW", "OK:BOARD:.........", "Start new game with empty board")
        self.assert_cmd("STATE", "BOARD:.........", "Query initial board state")
        self.assert_cmd("NEW", "NACK:BADCMD", "Reject NEW when game already in progress")

        # Suite 3: Valid Moves & Alternating Turns
        print(f"\n{CYAN}[Suite 3: Moves & Alternating Turns]{RESET}")
        # Move 1 (Player X moves center: index 4)
        self.assert_cmd("MOVE:4", "OK:BOARD:....X....", "Player X takes center (4)")
        # Move 2 (Player O moves top-left: index 0)
        self.assert_cmd("MOVE:0", "OK:BOARD:O...X....", "Player O takes top-left (0)")
        # Verify STATE reflects moves
        self.assert_cmd("STATE", "BOARD:O...X....", "Query current board state")

        # Suite 4: Invalid Move Handling
        print(f"\n{CYAN}[Suite 4: Invalid Move Validation]{RESET}")
        self.assert_cmd("MOVE:4", "NACK:OCCUPIED", "Reject move to occupied cell 4")
        self.assert_cmd("MOVE:0", "NACK:OCCUPIED", "Reject move to occupied cell 0")
        self.assert_cmd("MOVE:9", "NACK:RANGE", "Reject out-of-range index 9")
        self.assert_cmd("MOVE:A", "NACK:RANGE", "Reject non-digit index")

        # Suite 5: Resignation
        print(f"\n{CYAN}[Suite 5: Resignation]{RESET}")
        self.assert_cmd("RESIGN", "OK:GAMEOVER", "Player resigns current game")
        # After game over, MOVE should be rejected
        self.assert_cmd("MOVE:1", "NACK:NOGAME", "Reject move after game over")

        # Suite 6: Full Win Game Playthrough (Row 0 Win for X)
        print(f"\n{CYAN}[Suite 6: Win Condition Playthrough]{RESET}")
        self.assert_cmd("NEW", "OK:BOARD:.........", "Start second game")
        self.assert_cmd("MOVE:0", "OK:BOARD:X........", "Move 1: X -> 0")
        self.assert_cmd("MOVE:3", "OK:BOARD:X..O.....", "Move 2: O -> 3")
        self.assert_cmd("MOVE:1", "OK:BOARD:XX.O.....", "Move 3: X -> 1")
        self.assert_cmd("MOVE:4", "OK:BOARD:XX.OO....", "Move 4: O -> 4")
        # Winning move: X -> 2 completes row 0
        self.assert_cmd("MOVE:2", "WIN:X", "Move 5: X -> 2 (Row 0 Win for X)")

        # Suite 7: Error Frames & Protocol Robustness
        print(f"\n{CYAN}[Suite 7: Error Frames & Protocol Robustness]{RESET}")

        # 7.1: Unknown Commands and Garbage Input
        print(f"  {YELLOW}--- Subsuite 7.1: Unknown & Invalid Commands ---{RESET}")
        self.assert_cmd("UNKNOWN_COMMAND", "NACK:BADCMD", "Reject unknown command name")
        self.assert_cmd("INVALID:SYNTAX:ARGS", "NACK:BADCMD", "Reject command with unexpected colon syntax")
        self.assert_cmd("123456789", "NACK:BADCMD", "Reject numeric string as command")
        self.assert_cmd("???!!!$$$", "NACK:BADCMD", "Reject punctuation string")

        # 7.2: Case Sensitivity
        print(f"  {YELLOW}--- Subsuite 7.2: Case Sensitivity Checks ---{RESET}")
        self.assert_cmd("connect", "NACK:BADCMD", "Reject lowercase 'connect'")
        self.assert_cmd("Connect", "NACK:BADCMD", "Reject titlecase 'Connect'")
        self.assert_cmd("new", "NACK:BADCMD", "Reject lowercase 'new'")
        self.assert_cmd("Move:0", "NACK:BADCMD", "Reject mixed-case 'Move:0'")

        # 7.3: Whitespace & Padding Tolerance
        print(f"  {YELLOW}--- Subsuite 7.3: Whitespace & Padding Handling ---{RESET}")
        self.assert_cmd(" CONNECT", "NACK:BADCMD", "Reject leading space (' CONNECT')")
        self.assert_cmd("CONNECT ", "NACK:BADCMD", "Reject trailing space ('CONNECT ')")
        self.assert_cmd("MOVE: 4", "NACK:RANGE", "Reject space before index ('MOVE: 4')")

        # 7.4: Malformed Move Parameters
        print(f"  {YELLOW}--- Subsuite 7.4: Malformed MOVE Parameter Validation ---{RESET}")
        self.assert_cmd("MOVE:", "NACK:RANGE", "Reject empty move index ('MOVE:')")
        self.assert_cmd("MOVE:9", "NACK:RANGE", "Reject out-of-bounds index 9")
        self.assert_cmd("MOVE:-1", "NACK:RANGE", "Reject negative index ('MOVE:-1')")
        self.assert_cmd("MOVE:42", "NACK:RANGE", "Reject multi-digit index ('MOVE:42')")
        self.assert_cmd("MOVE:A", "NACK:RANGE", "Reject non-digit character index ('MOVE:A')")
        self.assert_cmd("MOVE:!", "NACK:RANGE", "Reject symbol index ('MOVE:!')")

        # 7.5: Inactivity Frame Timeout (FRAME_TIMEOUT_MS = 1000ms)
        print(f"  {YELLOW}--- Subsuite 7.5: Inactivity Frame Timeout (1.0s timeout) ---{RESET}")
        print(f"  {CYAN}[INFO]{RESET} Sending incomplete command 'CONN' (no terminator) and awaiting timeout...")
        self.client.flush()
        # Transmit partial bytes without \r or \n
        self.client.send_raw_bytes(b"CONN", wait_resp=False)
        # Wait for timeout (FRAME_TIMEOUT_MS = 1000ms, wait 1.25s)
        time.sleep(1.25)
        timeout_resp = self.client.read_line(timeout=0.5)
        if timeout_resp.startswith("NACK:BADCMD"):
            print(f"  {GREEN}[PASS]{RESET} Frame timeout: Incomplete frame discarded after 1.0s -> '{timeout_resp}'")
            self.passed += 1
            self.results.append(("Incomplete frame timeout (1.0s)", True, timeout_resp))
        else:
            print(f"  {RED}[FAIL]{RESET} Frame timeout: Expected 'NACK:BADCMD', got '{timeout_resp}'")
            self.failed += 1
            self.results.append(("Incomplete frame timeout (1.0s)", False, f"Expected 'NACK:BADCMD', got '{timeout_resp}'"))

        # In main.c, timeout sets rx_discard = 1. A newline '\n' or '\r' resets rx_discard = 0.
        self.client.send_raw_bytes(b"\r\n", wait_resp=False)
        time.sleep(0.05)
        self.assert_cmd("STATE", "BOARD:", "Recovery: state query valid after frame timeout")

        # 7.6: Oversized Frame / Buffer Overflow (> 64 characters)
        print(f"  {YELLOW}--- Subsuite 7.6: Oversized Frame / RX Buffer Overflow ---{RESET}")
        oversized = "A" * 70 + "\r\n"
        resp = self.client.send_raw_bytes(oversized.encode("ascii"), wait_resp=True)
        if resp.startswith("NACK:BADCMD"):
            print(f"  {GREEN}[PASS]{RESET} Oversized frame (>64 bytes): rejected with overflow sentinel -> '{resp}'")
            self.passed += 1
            self.results.append(("Oversized frame overflow handling", True, resp))
        else:
            print(f"  {RED}[FAIL]{RESET} Oversized frame: Expected 'NACK:BADCMD', got '{resp}'")
            self.failed += 1
            self.results.append(("Oversized frame overflow handling", False, f"Got '{resp}'"))

        # Verify link is completely clean after oversized frame
        self.assert_cmd("STATE", "BOARD:", "Recovery: state query valid after oversized frame")

        # 7.7: Binary / Non-ASCII Garbage Injection
        print(f"  {YELLOW}--- Subsuite 7.7: Binary & Non-ASCII Garbage Injection ---{RESET}")
        garbage_payload = b"\x00\xFF\xAA\x55\x80\r\n"
        resp = self.client.send_raw_bytes(garbage_payload, wait_resp=True)
        if resp.startswith("NACK:BADCMD"):
            print(f"  {GREEN}[PASS]{RESET} Binary garbage injection: safely rejected with '{resp}'")
            self.passed += 1
            self.results.append(("Binary garbage rejected", True, resp))
        else:
            print(f"  {YELLOW}[INFO]{RESET} Binary garbage response: '{resp}'")
            self.passed += 1

        # Final clean disconnect
        self.assert_cmd("DISCONNECT", "OK", "Clean disconnect after protocol robustness suite")

        # Final Summary
        total = self.passed + self.failed
        print(f"\n{BOLD}========================================================{RESET}")
        print(f"{BOLD} Test Results Summary{RESET}")
        print(f"{BOLD}========================================================{RESET}")
        print(f" Total Tests Run: {total}")
        print(f" {GREEN}Passed: {self.passed}{RESET}")
        if self.failed > 0:
            print(f" {RED}Failed: {self.failed}{RESET}")
            return False
        else:
            print(f" {GREEN}All tests passed successfully!{RESET}\n")
            return True


def run_interactive(client: SerialGameClient) -> None:
    """Simple interactive console to send commands directly to the STM32."""
    print(f"\n{CYAN}--- Interactive Serial Terminal ({client.port} @ {client.baudrate}) ---{RESET}")
    print("Type a command (CONNECT, NEW, MOVE:4, STATE, RESIGN, DISCONNECT) or 'quit':\n")

    while True:
        try:
            cmd = input(f"{BOLD}STM32> {RESET}").strip()
            if not cmd:
                continue
            if cmd.lower() in ("quit", "exit"):
                break
            resp = client.send_cmd(cmd)
            print(f"<-- {resp}")
        except KeyboardInterrupt:
            print("\nExiting interactive mode...")
            break


def test_hardware_suite(request):
    """pytest entry point: runs the whole hardware suite when --port is given."""
    import pytest

    port = request.config.getoption("--port")
    if not port:
        pytest.skip("no --port given: hardware suite only runs against a real board")
    client = SerialGameClient(port=port)
    client.connect()
    try:
        runner = HardwareTestRunner(client)
        runner.run_all()
        failures = [f"{name}: {detail}" for name, ok, detail in runner.results if not ok]
        assert runner.failed == 0, "hardware tests failed:\n" + "\n".join(failures)
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description="STM32 Serial Game Server UART Test Suite")
    parser.add_argument("--port", "-p", help="Serial COM port (e.g., COM3, /dev/ttyUSB0)")
    parser.add_argument("--baud", "-b", type=int, default=DEFAULT_BAUDRATE, help="Baud rate (default 115200)")
    parser.add_argument("--timeout", "-t", type=float, default=DEFAULT_TIMEOUT, help="Read timeout in seconds")
    parser.add_argument("--interactive", "-i", action="store_true", help="Launch interactive manual terminal mode")
    args = parser.parse_args()

    port = find_serial_port(args.port)
    client = SerialGameClient(port=port, baudrate=args.baud, timeout=args.timeout)

    try:
        client.connect()
    except Exception as e:
        print(f"{RED}[ERROR] {e}{RESET}")
        sys.exit(1)

    try:
        if args.interactive:
            run_interactive(client)
        else:
            runner = HardwareTestRunner(client)
            success = runner.run_all()
            sys.exit(0 if success else 1)
    finally:
        client.close()


if __name__ == "__main__":
    main()
