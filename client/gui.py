"""Tic-Tac-Toe client: a thin Tkinter GUI for the STM32 serial game server.

Run from the repo root:
    python client/gui.py                 # pick a port in the window
    python client/gui.py --port COM5     # preselect a port
    python client/gui.py --sim           # built-in simulator, no hardware
"""
from __future__ import annotations

import argparse
import queue
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from protocol import EMPTY_BOARD, Kind, Response, describe_nack, next_player
from serial_link import GameLink, LinkError, LinkTimeout, available_ports

SIMULATOR_LABEL = "Simulator (no board)"
POLL_MS = 40

# What the client believes the server's state is (the server stays authoritative).
DISCONNECTED, IDLE, IN_PROGRESS, GAME_OVER = "DISCONNECTED", "IDLE", "IN_PROGRESS", "GAME_OVER"

MARK_COLOURS = {"X": "#1f6feb", "O": "#d1242f", ".": "#222222"}


class GameApp:
    def __init__(self, root: tk.Tk, default_port: Optional[str] = None) -> None:
        self.root = root
        self.link: Optional[GameLink] = None
        self.phase = DISCONNECTED
        self.board = EMPTY_BOARD
        self.busy = False
        self._closed = False
        self._results: "queue.Queue[tuple]" = queue.Queue()

        self._build_widgets()
        self._refresh_ports(default_port)
        self._render()
        self._update_controls()
        self._set_status("Choose a port and press Connect.")
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.after(POLL_MS, self._poll)

    def _build_widgets(self) -> None:
        self.root.title("Tic-Tac-Toe: STM32 Serial Game Server")
        self.root.resizable(False, False)

        top = ttk.Frame(self.root, padding=(10, 10, 10, 4))
        top.grid(row=0, column=0, sticky="ew")
        ttk.Label(top, text="Port:").grid(row=0, column=0, padx=(0, 4))
        self.port_var = tk.StringVar()
        self.port_box = ttk.Combobox(top, textvariable=self.port_var, width=18, state="readonly")
        self.port_box.grid(row=0, column=1)
        self.refresh_btn = ttk.Button(top, text="Refresh", command=self._refresh_ports)
        self.refresh_btn.grid(row=0, column=2, padx=4)
        self.connect_btn = ttk.Button(top, text="Connect", width=10, command=self._on_connect_toggle)
        self.connect_btn.grid(row=0, column=3, padx=(4, 4))
        self.new_btn = ttk.Button(top, text="New Game", width=10, command=self._on_new)
        self.new_btn.grid(row=0, column=4, padx=(0, 4))
        self.resign_btn = ttk.Button(top, text="Resign", width=10, command=self._on_resign)
        self.resign_btn.grid(row=0, column=5)

        grid = ttk.Frame(self.root, padding=10)
        grid.grid(row=1, column=0)
        self.cells = []
        for i in range(9):
            btn = tk.Button(
                grid,
                text=" ",
                width=3,
                height=1,
                font=("Helvetica", 36, "bold"),
                relief="raised",
                bd=3,
                command=lambda i=i: self._on_cell(i),
            )
            btn.grid(row=i // 3, column=i % 3, padx=3, pady=3)
            self.cells.append(btn)

        self.status_var = tk.StringVar()
        self.status_lbl = tk.Label(
            self.root, textvariable=self.status_var, anchor="w", relief="sunken", bd=1, padx=8, pady=4
        )
        self.status_lbl.grid(row=2, column=0, sticky="ew")
        self.root.columnconfigure(0, weight=1)

    def _set_status(self, message: str, error: bool = False) -> None:
        self.status_var.set(message)
        self.status_lbl.config(fg="#b00020" if error else "#000000")

    def _render(self) -> None:
        """Draw self.board. Only ever called with a server-confirmed board."""
        for btn, mark in zip(self.cells, self.board):
            colour = MARK_COLOURS[mark]
            btn.config(text=" " if mark == "." else mark, fg=colour, disabledforeground=colour)

    def _update_controls(self) -> None:
        connected = self.phase != DISCONNECTED
        self.connect_btn.config(
            text="Disconnect" if connected else "Connect",
            state="disabled" if self.busy else "normal",
        )
        self.new_btn.config(state="normal" if connected and not self.busy else "disabled")
        self.resign_btn.config(state="normal" if connected and self.phase == IN_PROGRESS and not self.busy else "disabled")
        self.port_box.config(state="disabled" if connected or self.busy else "readonly")
        self.refresh_btn.config(state="disabled" if connected or self.busy else "normal")
        
        cell_state = "normal" if self.phase == IN_PROGRESS and not self.busy else "disabled"
        for btn in self.cells:
            btn.config(state=cell_state)

    def _refresh_ports(self, preselect: Optional[str] = None) -> None:
        ports = [SIMULATOR_LABEL] + available_ports()
        self.port_box.config(values=ports)
        current = preselect or self.port_var.get()
        if current in ports:
            self.port_var.set(current)
        elif preselect:                    
            self.port_box.config(values=ports + [preselect])
            self.port_var.set(preselect)
        else:
            self.port_var.set(ports[1] if len(ports) > 1 else ports[0])

    # ------------------------------------------------------ worker plumbing --
    def _submit(self, work: Callable[[], object], done: Callable[[object, Optional[Exception]], None]) -> None:
        """Run work() off the UI thread, then done(result, error) on the UI thread."""
        self.busy = True
        self._update_controls()

        def runner() -> None:
            try:
                result, error = work(), None
            except Exception as exc:  
                result, error = None, exc
            self._results.put((done, result, error))

        threading.Thread(target=runner, daemon=True).start()

    def _poll(self) -> None:
        try:
            while True:
                done, result, error = self._results.get_nowait()
                self.busy = False
                done(result, error)
                if self._closed:          
                    return
                self._update_controls()
        except queue.Empty:
            pass
        finally:
            if not self._closed:
                self.root.after(POLL_MS, self._poll)

    # --------------------------------------------------------------- events --
    def _on_connect_toggle(self) -> None:
        if self.phase == DISCONNECTED:
            self._connect()
        else:
            self._disconnect()

    def _connect(self) -> None:
        choice = self.port_var.get()
        if not choice:
            self._set_status("Choose a port first.", error=True)
            return
        link = GameLink.simulated() if choice == SIMULATOR_LABEL else GameLink(choice)

        def work() -> Response:
            link.open()
            try:
                return link.connect(recover=True)   
            except Exception:
                link.close()
                raise

        def done(resp, err) -> None:
            if err is not None:
                self._set_status(f"Could not connect: {err}", error=True)
                return
            if resp.kind is Kind.OK:
                self.link, self.phase, self.board = link, IDLE, EMPTY_BOARD
                self._render()
                self._set_status(f"Connected to {choice}. Press New Game to start.")
            else:
                link.close()
                self._set_status(f"The board refused CONNECT: {self._explain(resp)}", error=True)

        self._set_status(f"Connecting to {choice} ...")
        self._submit(work, done)

    def _on_new(self) -> None:
        if self.link is None or self.busy:
            return
        link, abandon = self.link, self.phase == IN_PROGRESS

        def work() -> Response:
            if abandon:                      
                resp = link.resign()
                if resp.kind is not Kind.GAMEOVER and not resp.is_terminal:
                    return resp
            return link.new_game()

        def done(resp, err) -> None:
            if err is not None:
                self._handle_link_error(err)
            elif resp.kind is Kind.OK_BOARD:
                self.phase, self.board = IN_PROGRESS, resp.board
                self._render()
                self._set_status(f"New game. {next_player(self.board)} to move.")
            else:
                self._show_refusal(resp)

        self._set_status("Starting a new game ...")
        self._submit(work, done)

    def _on_resign(self) -> None:
        if self.link is None or self.busy or self.phase != IN_PROGRESS:
            return
        link = self.link

        def work():
            resp = link.resign()
            final_board = None
            if resp.is_terminal and resp.board is None:   
                follow_up = link.state()
                if follow_up.kind is Kind.BOARD:
                    final_board = follow_up.board
            return resp, final_board

        def done(result, err) -> None:
            if err is not None:
                self._handle_link_error(err)
                return
            resp, final_board = result
            if resp.is_terminal or resp.kind is Kind.GAMEOVER:
                board = resp.board or final_board
                if board:
                    self.board = board
                self._render()
                self.phase = GAME_OVER
                
                winner = resp.winner
                if winner:
                    result_text = f"Player {winner} wins!\n(by Resignation)"
                else:
                    result_text = "Oponent Resigned."
                
                self._set_status(f"Player {winner} wins by resignation!" if winner else "Game Over!")
                self._show_game_over_popup(result_text)
            else:
                self._show_refusal(resp)

        self._set_status("Resigning game ...")
        self._submit(work, done)

    def _show_game_over_popup(self, result_text: str) -> None:
        """Modal popup displaying game results with New Game and Disconnect options."""
        popup = tk.Toplevel(self.root)
        popup.title("Game Over")
        popup.geometry("320x160")
        popup.resizable(False, False)
        popup.transient(self.root)
        popup.grab_set()

        # Restored original popup text format: "Game Over!\n\n<result_text>"
        lbl = tk.Label(popup, text=f"Game Over!\n\n{result_text}", font=("Helvetica", 11), pady=15)
        lbl.pack(fill="x")

        btn_frame = ttk.Frame(popup, padding=10)
        btn_frame.pack(fill="x", expand=True)

        def on_new():
            popup.destroy()
            self._on_new()

        def on_disc():
            popup.destroy()
            self._disconnect()

        btn_new = ttk.Button(btn_frame, text="New Game", command=on_new, width=12)
        btn_new.pack(side="left", padx=10, expand=True)

        btn_disc = ttk.Button(btn_frame, text="Disconnect", command=on_disc, width=12)
        btn_disc.pack(side="right", padx=10, expand=True)

    def _on_cell(self, index: int) -> None:
        if self.link is None or self.busy or self.phase != IN_PROGRESS:
            return
        link = self.link

        def work():
            resp = link.move(index)
            final_board = None
            if resp.is_terminal and resp.board is None:   
                follow_up = link.state()
                if follow_up.kind is Kind.BOARD:
                    final_board = follow_up.board
            return resp, final_board

        def done(result, err) -> None:
            if err is not None:
                self._handle_link_error(err)
                return
            resp, final_board = result
            if resp.kind is Kind.OK_BOARD:
                self.board = resp.board
                self._render()
                self._set_status(f"{next_player(self.board)} to move.")
            elif resp.is_terminal or resp.kind is Kind.GAMEOVER:
                board = resp.board or final_board
                if board:
                    self.board = board
                self._render()
                self.phase = GAME_OVER
                
                result_text = f"Player {resp.winner} wins!" if resp.winner else "It's a draw."
                self._set_status(f"{result_text} Press New Game to play again.")
                self._show_game_over_popup(result_text)
            else:
                self._show_refusal(resp)

        self._set_status(f"Sending move to cell {index} ...")
        self._submit(work, done)

    def _disconnect(self, then: Optional[Callable[[], None]] = None) -> None:
        link, phase = self.link, self.phase

        def work() -> None:
            if link is None:
                return
            try:
                if phase == IN_PROGRESS:
                    link.resign()
                    link.disconnect()
                elif phase == GAME_OVER:
                    link.disconnect()
            finally:
                link.close()

        def done(_result, err) -> None:
            self.link, self.phase, self.board = None, DISCONNECTED, EMPTY_BOARD
            self._render()
            if err is not None:
                self._set_status(f"Disconnected (with a problem: {err})", error=True)
            else:
                self._set_status("Disconnected.")
            if then is not None:
                then()

        self._set_status("Disconnecting ...")
        self._submit(work, done)

    def _on_close(self) -> None:
        if self.link is not None and not self.busy:
            self._disconnect(then=self._destroy)   
        else:
            self._destroy()

    def _destroy(self) -> None:
        self._closed = True
        self.root.destroy()

    @staticmethod
    def _explain(resp: Response) -> str:
        if resp.kind is Kind.NACK:
            return describe_nack(resp.reason)
        return f"unexpected reply {resp.raw!r}"

    def _show_refusal(self, resp: Response) -> None:
        """A NACK or an unexpected reply: say why, and leave the board alone."""
        if resp.kind is Kind.NACK and resp.reason == "NOGAME":
            self.phase = IDLE                  # server has no running game: resync
        self._set_status(self._explain(resp), error=True)

    def _handle_link_error(self, err: Exception) -> None:
        if isinstance(err, LinkTimeout):
            self._set_status("No response from the board (timeout). Check the cable and try again.", error=True)
        elif isinstance(err, LinkError):
            if self.link is not None:
                self.link.close()
            self.link, self.phase, self.board = None, DISCONNECTED, EMPTY_BOARD
            self._render()
            self._set_status(f"Serial connection lost: {err}", error=True)
        else:
            self._set_status(f"Unexpected error: {err}", error=True)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Tic-Tac-Toe client for the STM32 serial game server")
    parser.add_argument("--port", help="serial port to preselect (e.g. COM5, /dev/ttyUSB0)")
    parser.add_argument("--sim", action="store_true", help="preselect the built-in simulator")
    args = parser.parse_args(argv)

    root = tk.Tk()
    GameApp(root, default_port=SIMULATOR_LABEL if args.sim else args.port)
    root.mainloop()


if __name__ == "__main__":
    main()