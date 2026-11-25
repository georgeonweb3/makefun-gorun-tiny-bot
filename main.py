#!/usr/bin/env python3
"""Laggard Ladder — a tiny paper-trading bot for make.fun's
"Tiny Bot, Easy $2: Beat Buy-and-Hold on Solana" bounty.

Speaks agent-fun/bars-replay/v1 on stdin/stdout: the harness sends a
hello line, then one batch of hourly bars per line, then done; the bot
answers every batch with one reply line echoing its seq and the orders
decided on that batch. See vendor/strategy.py for the strategy and
vendor/makefun_bars.py for the protocol shim (a byte copy of the kit SDK).

Run it: python3 main.py < bars.ndjson (or let the grader drive it).
Standard library only; deterministic — no clock, no randomness, no
network, no environment reads. Same bars in, same orders out.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import makefun_bars  # noqa: E402
from strategy import Bot  # noqa: E402

makefun_bars.run(Bot().on_batch)  # one reply per batch, orders fill at next bar's open

