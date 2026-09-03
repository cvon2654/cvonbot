"""
Always-on-top floating overlay for Windows: a small draggable, resizable
panel showing live edges/scores/headlines, meant to sit in a corner of
your screen while you watch the game or have Kalshi open elsewhere.

Same read-only guarantee as src/main.py -- this window only displays what
`gather()` returns. It never places an order.

Usage:
    python -m src.overlay --config config.yaml

Requires Tk, which ships with the official python.org Windows installer.
If you installed Python from the Microsoft Store and `import tkinter`
fails, reinstall from python.org and check "tcl/tk and IDLE".
"""

from __future__ import annotations

import argparse
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import font as tkfont

from dotenv import load_dotenv

from .main import build_client, gather, load_config

BG = "#111418"
BG_PANEL = "#1a1f26"
FG = "#e7ebef"
FG_DIM = "#8a94a3"
GREEN = "#4fd67a"
RED = "#e0645a"
ACCENT = "#3f8cff"

WIDTH_DEFAULT = 360
HEIGHT_DEFAULT = 440
MIN_WIDTH = 260
MIN_HEIGHT = 200


class Poller(threading.Thread):
    """Runs gather() on a timer in the background so network calls never block the UI."""

    def __init__(self, cfg: dict, client, out_queue: "queue.Queue", stop_event: threading.Event):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.client = client
        self.out_queue = out_queue
        self.stop_event = stop_event

    def run(self) -> None:
        interval = self.cfg.get("poll_interval_seconds", 30)
        while not self.stop_event.is_set():
            try:
                result = gather(self.cfg, self.client)
                self.out_queue.put(("ok", result))
            except Exception as exc:  # keep polling even if one round fails
                self.out_queue.put(("error", str(exc)))
            self.stop_event.wait(interval)


class OverlayApp:
    def __init__(self, cfg: dict, client):
        self.cfg = cfg
        self.client = client
        self.data_queue: "queue.Queue" = queue.Queue()
        self.stop_event = threading.Event()

        self.root = tk.Tk()
        self.root.overrideredirect(True)  # no OS title bar/frame
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-alpha", 0.92)  # slight transparency (Windows)
        except tk.TclError:
            pass  # not supported on this platform/backend; window stays opaque

        screen_w = self.root.winfo_screenwidth()
        x = screen_w - WIDTH_DEFAULT - 24
        y = 24
        self.root.geometry(f"{WIDTH_DEFAULT}x{HEIGHT_DEFAULT}+{x}+{y}")
        self.root.configure(bg=BG)
        self.root.minsize(MIN_WIDTH, MIN_HEIGHT)

        self._build_ui()
        self._wire_drag_and_resize()

        self.root.after(100, self._drain_queue)

    # -- UI construction ---------------------------------------------------

    def _build_ui(self) -> None:
        mono = tkfont.Font(family="Consolas", size=9)
        mono_bold = tkfont.Font(family="Consolas", size=9, weight="bold")
        title_font = tkfont.Font(family="Segoe UI", size=10, weight="bold")

        # Drag handle / title bar
        handle = tk.Frame(self.root, bg=BG_PANEL, height=28)
        handle.pack(fill="x", side="top")
        handle.pack_propagate(False)
        tk.Label(handle, text="Kalshi Live", bg=BG_PANEL, fg=FG, font=title_font).pack(side="left", padx=8)
        self.status_label = tk.Label(handle, text="starting...", bg=BG_PANEL, fg=FG_DIM, font=mono)
        self.status_label.pack(side="left", padx=6)
        close_btn = tk.Label(handle, text="✕", bg=BG_PANEL, fg=FG_DIM, font=title_font, cursor="hand2")
        close_btn.pack(side="right", padx=8)
        close_btn.bind("<Button-1>", lambda e: self.close())
        self._drag_handle = handle

        # Scrollable body
        body_wrap = tk.Frame(self.root, bg=BG)
        body_wrap.pack(fill="both", expand=True)
        canvas = tk.Canvas(body_wrap, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(body_wrap, orient="vertical", command=canvas.yview)
        self.body = tk.Frame(canvas, bg=BG)
        self.body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.body, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._canvas = canvas

        self._mono = mono
        self._mono_bold = mono_bold

        self._section("Live games", "games_frame")
        self._section("Top edges", "edges_frame")
        self._section("Headlines", "news_frame")

        # Resize grip, bottom-right corner. Cursor name differs by platform --
        # "sizing" is the Windows one this is built for; fall back quietly elsewhere.
        grip = tk.Label(self.root, text="◢", bg=BG_PANEL, fg=FG_DIM)
        try:
            grip.configure(cursor="sizing")
        except tk.TclError:
            pass
        grip.place(relx=1.0, rely=1.0, anchor="se")
        self._grip = grip

    def _section(self, title: str, attr_name: str) -> None:
        header = tk.Label(self.body, text=title.upper(), bg=BG, fg=ACCENT,
                           font=tkfont.Font(family="Segoe UI", size=8, weight="bold"))
        header.pack(anchor="w", padx=8, pady=(10, 2))
        frame = tk.Frame(self.body, bg=BG)
        frame.pack(fill="x", padx=8)
        setattr(self, attr_name, frame)

    def _wire_drag_and_resize(self) -> None:
        drag_state = {"x": 0, "y": 0}

        def start_drag(event):
            drag_state["x"] = event.x
            drag_state["y"] = event.y

        def do_drag(event):
            x = self.root.winfo_x() + (event.x - drag_state["x"])
            y = self.root.winfo_y() + (event.y - drag_state["y"])
            self.root.geometry(f"+{x}+{y}")

        self._drag_handle.bind("<ButtonPress-1>", start_drag)
        self._drag_handle.bind("<B1-Motion>", do_drag)

        resize_state = {"x": 0, "y": 0, "w": 0, "h": 0}

        def start_resize(event):
            resize_state.update(x=event.x_root, y=event.y_root,
                                 w=self.root.winfo_width(), h=self.root.winfo_height())

        def do_resize(event):
            new_w = max(MIN_WIDTH, resize_state["w"] + (event.x_root - resize_state["x"]))
            new_h = max(MIN_HEIGHT, resize_state["h"] + (event.y_root - resize_state["y"]))
            self.root.geometry(f"{new_w}x{new_h}")

        self._grip.bind("<ButtonPress-1>", start_resize)
        self._grip.bind("<B1-Motion>", do_resize)

    # -- data -> UI ----------------------------------------------------------

    def _clear(self, frame: tk.Frame) -> None:
        for child in frame.winfo_children():
            child.destroy()

    def _row(self, frame: tk.Frame, text: str, color: str = FG, bold: bool = False) -> None:
        lbl = tk.Label(frame, text=text, bg=BG, fg=color, font=(self._mono_bold if bold else self._mono),
                        justify="left", anchor="w", wraplength=WIDTH_DEFAULT - 40)
        lbl.pack(fill="x", anchor="w", pady=1)

    def _render(self, games: list, edges: list, headlines: list, portfolio, warnings: list) -> None:
        self._clear(self.games_frame)
        if not games:
            self._row(self.games_frame, "No live games in scope.", FG_DIM)
        for g in games[:8]:
            score = f"{g['away_abbrev']} {g['away_score']}-{g['home_score']} {g['home_abbrev']}"
            self._row(self.games_frame, f"{score:<16} {g.get('detail') or g.get('state') or ''}")

        self._clear(self.edges_frame)
        if not edges:
            self._row(self.edges_frame, "No edges above threshold.", FG_DIM)
        for e in sorted(edges, key=lambda x: x["stake"].edge_pct, reverse=True)[:6]:
            stake = e["stake"]
            color = GREEN if stake.edge_pct > 0 else RED
            self._row(self.edges_frame, e["title"][:34], FG, bold=True)
            self._row(
                self.edges_frame,
                f"  model {e['model_prob']:.0%}  kalshi {e['market_prob']:.0%}  "
                f"edge {stake.edge_pct:+.1%}  ${stake.suggested_usd:,.0f}",
                color,
            )

        self._clear(self.news_frame)
        if not headlines:
            self._row(self.news_frame, "No related headlines yet.", FG_DIM)
        for h in headlines[:6]:
            self._row(self.news_frame, f"• {h['title'][:44]}", FG_DIM)

        if portfolio and portfolio.get("balance_usd") is not None:
            self.status_label.configure(text=f"${portfolio['balance_usd']:,.2f}")
        else:
            self.status_label.configure(text=time.strftime("%H:%M:%S"))

    def _drain_queue(self) -> None:
        try:
            while True:
                kind, payload = self.data_queue.get_nowait()
                if kind == "ok":
                    games, edges, headlines, portfolio, warnings = payload
                    self._render(games, edges, headlines, portfolio, warnings)
                else:
                    self.status_label.configure(text="error", fg=RED)
        except queue.Empty:
            pass
        self.root.after(500, self._drain_queue)

    # -- lifecycle -------------------------------------------------------

    def close(self) -> None:
        self.stop_event.set()
        self.root.destroy()

    def run(self) -> None:
        poller = Poller(self.cfg, self.client, self.data_queue, self.stop_event)
        poller.start()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Floating always-on-top Kalshi overlay (Windows).")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    load_dotenv()
    if not os.path.exists(args.config):
        raise SystemExit(f"Missing {args.config} -- copy config.example.yaml to {args.config} first.")

    cfg = load_config(args.config)
    client = build_client(cfg)
    OverlayApp(cfg, client).run()


if __name__ == "__main__":
    main()
