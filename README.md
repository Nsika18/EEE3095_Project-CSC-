# Serial Game Server: Tic-Tac-Toe on an STM32

EEE3095S CSC Project, University of Cape Town.

A small game server running on an **STM32F051** board, and a thin **Python/Tkinter GUI** on the PC that plays against it over a serial (UART) link. The game is **Tic-Tac-Toe**.

The board is the referee. It stores the one true game state and enforces every rule. The GUI only forwards what the player clicks and draws what the board confirms. It never decides whether a move is legal.

```
 Player ──click──▶  GUI (Python, Tkinter)  ──serial text lines──▶  STM32 server (C)
                         ▲   pyserial                    UART          rules + game state
                         └──────── confirmed board, WIN / DRAW, NACK ────────┘
```

## Features

- Server on the STM32 holds the board, the turn, the win/draw logic and the state machine (IDLE, IN_PROGRESS, GAME_OVER).
- GUI with port selection, Connect/Disconnect, New Game, a 3×3 board and a status bar.
- The board is redrawn only from a valid server reply. A rejected move (`NACK`) shows a message and leaves the board untouched.
- Pop-up on win or draw with **New Game** and **Disconnect** buttons. The board stays disabled until a new game starts.
- Built-in **simulator** of the server, so the GUI and the tests run with no hardware.
- Automated **pytest** suite that runs against the simulator or the real board.

## Repository layout

```
.
├── firmware/            STM32CubeIDE project for the server (STM32F051, C)
├── client/
│   ├── gui.py           Tkinter window
│   ├── serial_link.py   pyserial wrapper, shared by the GUI and the tests
│   ├── protocol.py      message formats and reply parser
│   ├── simulator.py     in-process stand-in for the STM32 server
│   └── requirements.txt Python dependencies
├── tests/               pytest suite (protocol, full games, robustness)
├── docs/                protocol specification, plan, diagrams
├── report/              project report (LaTeX)
└── pytest.ini
```

## Requirements

| For | You need |
|---|---|
| The GUI and the tests | Python 3.9 or newer (Tkinter is included with the python.org installer for Windows and macOS; on Debian/Ubuntu run `sudo apt install python3-tk`) |
| The real board | An STM32F051 board, STM32CubeIDE, and a USB-to-UART adapter (3.3 V logic) |

## Quick start

### 1. Clone the repository

```bash
git clone https://github.com/Nsika18/EEE3095_Project-CSC-.git
cd EEE3095_Project-CSC-
```

### 2. Set up the Python environment

```bash
# Create a virtual environment (optional but recommended)
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # Linux / macOS

# Install the dependencies
pip install -r client/requirements.txt
```

### 3. Run the GUI with the built-in simulator (no hardware needed)

```bash
python client/gui.py --sim
```

Press **Connect**, then **New Game**, then click cells.

## Running with the real STM32 board

### Build and flash the server

1. Open **STM32CubeIDE**.
2. Choose **File → Open Projects from File System...**
3. Click **Directory...**, select the server project folder (`firmware/`), tick the project, and click **Finish**.
4. Build the project, then flash it to the board (**Run**).

### Wire the board to the PC

| STM32F051 | USB-to-UART adapter |
|---|---|
| `PA9` (USART1 TX) | `RXD` |
| `PA10` (USART1 RX) | `TXD` |
| `GND` | `GND` |

- TX goes to RX and RX goes to TX. The ground connection is mandatory.
- Do not connect the adapter's VCC if the board is already powered over USB.
- Both sides must be 3.3 V. A 5 V signal into `PA10` can damage the MCU.

Serial settings: **115200 baud, 8 data bits, no parity, 1 stop bit, no flow control (8N1)**.

### Start the client

1. Find the port: on Windows open **Device Manager → Ports (COM & LPT)** (for example `COM9`); on Linux look for `/dev/ttyUSB0`.
2. Launch the client with that port:

   ```bash
   python client/gui.py --port COM9
   ```

   or launch `python client/gui.py` and pick the port from the drop-down in the window.

## Running the tests

Run from the repository root.

```bash
# Against the built-in simulator
python -m pytest

# Against the real board (same tests)
python -m pytest --port COM9
```

The tests cover the session commands, legal and illegal moves, every winning line for both players, a draw, game-over handling, and malformed or oversized input. Make sure no other program (including the GUI) has the serial port open while the tests run.

## Protocol

Messages are single ASCII text lines in both directions, so the server can also be tested by hand from a serial terminal (PuTTY, `screen`, `minicom`). The commands are `CONNECT`, `NEW`, `MOVE`, `STATE`, `RESIGN` and `DISCONNECT`, and the server answers with the board, `WIN`/`DRAW`, or a `NACK` with a reason. The full specification, with the state machine and examples, is in [`docs/protocol.md`](docs/protocol.md).

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'serial'` | Install **pyserial** (`pip install pyserial`), not the unrelated package called `serial`. If you installed that one, run `pip uninstall serial` first. |
| Packages install but the GUI still cannot import them | You have more than one Python. Install with the same interpreter you run: `python -m pip install -r client/requirements.txt`. |
| The board's COM port is missing from the drop-down | Plug the board in, then press **Refresh**. Check that it appears in Device Manager. |
| `could not open port` or `Access is denied` | Another program has the port open (PuTTY, the CubeIDE console, another copy of the GUI). Close it. |
| Connect times out | Check that TX and RX are crossed, that GND is connected, that the firmware is running, and that the baud rate is 115200. |
| Linux: permission denied on `/dev/ttyUSB0` | `sudo usermod -aG dialout $USER`, then log out and back in. |
| Linux: `No module named 'tkinter'` | `sudo apt install python3-tk` |

## Course

EEE3095S, Department of Electrical Engineering, University of Cape Town, 2026.
