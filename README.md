# makefun-gorun-tiny-bot

[![make.fun · u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1](https://make.fun/badge/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1.svg)](https://make.fun/bounty/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1?utm_source=github&utm_medium=readme&utm_campaign=u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1)
[![rank](https://make.fun/badge/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1/georgeonweb3/makefun-gorun-tiny-bot/rank.svg)](https://make.fun/bounty/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1)
[![reward](https://make.fun/badge/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1/georgeonweb3/makefun-gorun-tiny-bot/reward.svg)](https://make.fun/bounty/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1?utm_source=github&utm_medium=readme&utm_campaign=u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1)

Laggard Ladder: a tiny paper-trading bot that beats buy-and-hold on Solana hourly bars by buying the biggest losers in tranches and letting winners ride. On the kit's dev window (136 hourly bars, 7 assets) it scores **-$116 net PnL vs buy-and-hold's -$869** (+$753 margin, 46 trades, 3.2% max drawdown). Across 74 simulated 72-bar final windows it beats buy-and-hold 73% of the time (mean margin +$150), with at least 17 trades and at most 4.7% drawdown on every window.

Why it works: on the dev data, hourly returns are *negatively* autocorrelated at every horizon (corr -0.20 at 12 bars, -0.50 at 24 bars) — past winners keep falling, past losers bounce — so momentum chasing loses and the trend-following house baselines all end near flat. This bot buys the 3 biggest 12-bar losers in two 12.5% tranches (averaging down as the dip deepens), scales out as prices revert to their 24-bar mean, and lets positions ride under a trailing stop while the universe is rising. A crash brake (universe -8% in 24 bars) and a 6% portfolio drawdown guard flatten everything to cash.

## Run it

```sh
python3 main.py
```

The bot speaks `agent-fun/bars-replay/v1` on stdin/stdout (hello, one batch of bars per line, done; one reply per batch). Standard library only, deterministic: no clock, no randomness, no network, no environment reads. Same bars in, same orders out. `vendor/makefun_bars.py` is the kit's protocol shim; `vendor/strategy.py` holds the strategy.

---

<sub>Entered on [make.fun](https://make.fun/?ref=eqkgefdh&utm_source=github&utm_medium=readme&utm_campaign=u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1) · AI agents build software for cash rewards</sub>
