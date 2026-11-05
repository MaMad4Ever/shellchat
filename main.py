#!/usr/bin/env python3
# Standard library
import argparse
import base64
import hashlib
import json
import re
import sys
import threading
import time
import uuid

from dataclasses import dataclass
from functools import lru_cache
from typing import Tuple

# External Library
import colorama
import redis

from colorama import Cursor, Fore, Style
from colorama.ansi import clear_line, clear_screen

# Make ANSI colors work on Windows too (no-op on Linux/macOS terminals).
colorama.init()

# constants
DIM, RESET = Style.DIM, Style.RESET_ALL
YELLOW, RED = Fore.LIGHTYELLOW_EX, Fore.LIGHTRED_EX


@dataclass(frozen=True)
class Theme:
    primary: str
    palette: Tuple[str, ...]


# Ready-made themes - pick one via --theme or /theme
THEMES = {
    "matrix": Theme(Fore.LIGHTGREEN_EX, (Fore.LIGHTGREEN_EX, Fore.GREEN,
                                         Fore.LIGHTWHITE_EX, Fore.LIGHTCYAN_EX)),
    "cyber":  Theme(Fore.LIGHTCYAN_EX, (Fore.LIGHTCYAN_EX, Fore.LIGHTMAGENTA_EX,
                                        Fore.LIGHTBLUE_EX, Fore.LIGHTYELLOW_EX,
                                        Fore.LIGHTGREEN_EX, Fore.LIGHTRED_EX)),
    "blood":  Theme(Fore.LIGHTRED_EX, (Fore.LIGHTRED_EX, Fore.RED,
                                       Fore.LIGHTMAGENTA_EX, Fore.LIGHTWHITE_EX)),
    "ice":    Theme(Fore.LIGHTBLUE_EX, (Fore.LIGHTBLUE_EX, Fore.LIGHTCYAN_EX,
                                        Fore.CYAN, Fore.LIGHTWHITE_EX)),
    "mono":   Theme(Fore.LIGHTWHITE_EX, (Fore.LIGHTWHITE_EX, Fore.WHITE)),
}
DEFAULT_THEME = "matrix"

# Limits - truncate long stuff so we don't choke the network/terminal
MAX_MSG_LEN = 2000
MAX_NAME_LEN = 20
MAX_BACKOFF = 30   # cap (seconds) for the reconnect delay

# Matches ASCII control characters (including ESC, which starts ANSI sequences).
# Used to stop remote users from injecting terminal escape codes.
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")

BANNER_ART = r"""
 ____   _   _  _____  _      _       ____  _   _     _     _____
/ ___| | | | || ____|| |    | |     / ___|| | | |   / \   |_   _|
\___ \ | |_| ||  _|  | |    | |    | |    | |_| |  / _ \    | |
 ___) ||  _  || |___ | |___ | |___ | |___ |  _  | / ___ \   | |
|____/ |_| |_||_____||_____||_____| \____||_| |_|/_/   \_\  |_|
"""


def banner(theme: Theme) -> str:
    """Render the banner using the current theme's accent color."""
    return (f"{theme.primary}{BANNER_ART}{RESET}"
            f"{DIM}  // redis pub/sub . no logs{RESET}\n")


# Lock stdout so the listener thread and the input loop never interleave.
print_lock = threading.Lock()


# helpers
def clean(text: str, limit: int) -> str:
    return CONTROL_CHARS.sub("", str(text))[:limit]


@lru_cache(maxsize=512)
def color_for(name: str, theme: Theme) -> str:
    digest = hashlib.md5(name.encode()).digest()
    encoded = base64.b64encode(digest)
    idx = int.from_bytes(encoded[:4], "big")
    return theme.palette[idx % len(theme.palette)]


class Chat:
    def __init__(self, client: redis.Redis, room: str, name: str,
                 theme: str = DEFAULT_THEME):
        self.redis_client = client
        self.room = room
        self.name = clean(name, MAX_NAME_LEN) or "anon"

        # Hash the room name so it doesn't show up in PUBSUB CHANNELS.
        # urlsafe chosen so '+' and '/' don't cause trouble in the channel name.
        encoded = base64.urlsafe_b64encode(
            hashlib.sha256(room.encode()).digest()
        ).decode()
        self.channel = "c:" + encoded[:12]

        # Random per-session id - used to ignore our own echoed messages.
        self.my_id = uuid.uuid4().hex
        self.stop = threading.Event()
        self.theme = THEMES[theme]
        self.theme_name = theme

    # output
    @property
    def prompt(self) -> str:
        return f"{self.theme.primary}{self.name}@{self.channel}{RESET}$ "

    def show(self, line: str) -> None:
        from_listener = threading.current_thread() is not threading.main_thread()
        with print_lock:
            if from_listener:
                sys.stdout.write(f"\r{clear_line()}{line}\n{self.prompt}")
            else:
                sys.stdout.write(f"{line}\n")
            sys.stdout.flush()

    def create_payload(self, text: str, system: bool = False) -> str:
        return json.dumps({
            "id": self.my_id,
            "name": self.name,
            "msg": text[:MAX_MSG_LEN],
            "ts": time.time(),
            "sys": system,
        })
    # sending
    def send(self, text: str, system: bool = False) -> None:
        payload = self.create_payload(text, system)

        try:
            self.redis_client.publish(self.channel, payload)
        except redis.RedisError as exc:
            self.show(f"{RED}[!] send failed: {exc}{RESET}")

    def parse_message(self, raw: str) -> dict | None:
        try:
            data = json.loads(raw)

            if data["id"] == self.my_id:
                return None

            return {
                "name": clean(data["name"], MAX_NAME_LEN),
                "msg": clean(data["msg"], MAX_MSG_LEN),
                "timestamp": float(data["ts"]),
                "is_system": bool(data.get("sys")),
            }

        except (ValueError, KeyError, TypeError):
            return None
    
    # receiving
    def render(self, raw: str) -> None:
        data = self.parse_message(raw)

        if data is None:
            return
        
        stamp = time.strftime(
            "%H:%M:%S",
            time.localtime(data["timestamp"])
        )

        name = data["name"]
        msg = data["msg"]

        if data["is_system"]:
            self.show(f"{DIM}[{stamp}] -- {name} {msg}{RESET}")
            return

        colored = color_for(name, self.theme)
        self.show(f"{DIM}[{stamp}]{RESET} {colored}<{name}>{RESET} {msg}")

    def listen(self) -> None:
        """Background thread: subscribe and auto-reconnect with backoff."""
        backoff = 1
        while not self.stop.is_set():
            pubsub = None
            try:
                pubsub = self.redis_client.pubsub(ignore_subscribe_messages=True)
                pubsub.subscribe(self.channel)
                backoff = 1                 # connected: reset the delay
                while not self.stop.is_set():
                    # Short timeout so we notice stop quickly
                    message = pubsub.get_message(timeout=1.0)
                    if message and message.get("type") == "message":
                        self.render(message["data"])
            except redis.RedisError as exc:
                self.show(f"{YELLOW}[~] connection lost ({exc}); "
                          f"retrying in {backoff}s{RESET}")
                self.stop.wait(backoff)     # interruptible sleep
                backoff = min(backoff * 2, MAX_BACKOFF)
            finally:
                # Always close the pubsub, or connections pile up
                if pubsub is not None:
                    try:
                        pubsub.close()
                    except redis.RedisError:
                        pass

    # themes 
    def list_themes(self) -> None:
        """Show every theme in its own colors; mark the active one with '*'."""
        rows = []
        for key, theme in THEMES.items():
            mark = "*" if key == self.theme_name else " "
            # Small palette preview
            sample = " ".join(f"{c}@user{RESET}" for c in theme.palette[:3])
            rows.append(f"  {mark} {theme.primary}{key:<7}{RESET} {sample}")
        self.show("themes (use /theme NAME):\n" + "\n".join(rows))

    def set_theme(self, key: str) -> None:
        """Switch theme if valid, otherwise show the list."""
        key = key.strip().lower()
        if key not in THEMES:
            self.show(f"{YELLOW}[~] unknown theme '{clean(key, 20)}'{RESET}")
            self.list_themes()
            return
        self.theme, self.theme_name = THEMES[key], key
        self.show(f"{self.theme.primary}[+] theme set to {key}{RESET}")

    # main loop
    def run(self) -> None:
        threading.Thread(target=self.listen, daemon=True).start()

        print(banner(self.theme))
        print(f"{DIM}room={self.room}   /nick NAME  /theme [NAME]  /clear  /quit{RESET}\n")
        self.send("connected", system=True)
        try:
            while True:
                line = input(self.prompt).strip()
                if line == "/quit":
                    break
                elif line == "/clear":
                    # Wipe the screen and send the cursor home
                    print(clear_screen() + Cursor.POS(), end="")
                elif line == "/theme":
                    self.list_themes()
                elif line.startswith("/theme "):
                    self.set_theme(line[7:])
                elif line.startswith("/nick "):
                    new = clean(line[6:], MAX_NAME_LEN).strip()
                    if new:
                        old, self.name = self.name, new
                        self.send(f"{old} is now {new}", system=True)
                elif line:
                    self.send(line)
        except (KeyboardInterrupt, EOFError):
            pass                    # Ctrl+C or Ctrl+D = quit
        finally:
            self.send("disconnected", system=True)
            self.stop.set()


# main
def main() -> None:
    parser = argparse.ArgumentParser(description="Hacker-style chat over Redis PUB/SUB")
    # --host is required: we can't connect without a server address
    parser.add_argument("--host", required=True, help="Redis host")
    parser.add_argument("--port", type=int, default=6379, help="Redis port")
    parser.add_argument("--password", default=None, help="Redis AUTH password")
    parser.add_argument("--tls", action="store_true", help="connect to Redis over TLS")
    parser.add_argument("--room", default="general", help="room name (must match)")
    parser.add_argument("--name", default=f"ghost{uuid.uuid4().hex[:3]}", help="your nickname")
    parser.add_argument("--theme", default=DEFAULT_THEME, choices=sorted(THEMES),
                   help="color theme (can be changed later with /theme)")
    args = parser.parse_args()

    client = redis.Redis(
        host=args.host, port=args.port, password=args.password, ssl=args.tls,
        decode_responses=True,
        socket_keepalive=True,        # detect dead TCP connections sooner
        health_check_interval=30,     # ping idle connections every 30s
    )
    try:
        client.ping()                 # fail fast if Redis is unreachable
    except redis.RedisError as exc:
        sys.exit(f"{RED}[!] cannot connect to Redis: {exc}{RESET}")

    Chat(client, args.room, args.name, args.theme).run()


if __name__ == "__main__":
    main()
