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
