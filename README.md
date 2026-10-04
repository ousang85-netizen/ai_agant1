# Stock Trading AI Agent

This project is a Python-based AI agent for stock trading. It includes modules for data retrieval, model training, and order execution. The structure is scaffolding and should be expanded with actual trading logic and machine learning models.

## Getting Started

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the main agent:
   ```bash
   python -m src.agent
   ```
   The agent will log current stock and option holdings (stubbed) and
   evaluate a simple weekly SMA strategy for AAPL.

3. Fill in the modules with your trading strategies and AI model, and
   implement real account integration via `src/fidelity.py`.

## Schwab Configuration

Set `SCHWAB_APP_KEY` and `SCHWAB_APP_SECRET` in the environment before
creating a `SchwabClient`. For example, in PowerShell:

```powershell
$env:SCHWAB_APP_KEY = "<your Schwab app key>"
$env:SCHWAB_APP_SECRET = "<your Schwab app secret>"
```

Shared Schwab settings and trading constants are defined in `src/constants.py`.

## Check EMA Duration

Count the most recent consecutive daily bars where a stock's closing price
is strictly above its 10-period EMA:

```bash
python -m src.ema_duration AAPL
```

Use `--interval 1wk` to count weekly bars, or `--period 20` to use a
20-period EMA. The calculation is read-only and does not place trades.
