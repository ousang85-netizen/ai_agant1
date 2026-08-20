"""Entry point for the stock trading AI agent."""

# This file has been cleared as requested. Fill in trading logic here.

import threading
from typing import Dict, Any, List
from xmlrpc import client
import pandas as pd
import time
import os
import re

import data
from schwab import SchwabClient
from ticker_scanner import collect_all_exchange_tickers
from technical_analyze import TechnicalAnalyzer


class TradingAgent:

    def __init__(self):
        pass

    def background_task(self, stop_event):
        ta = TechnicalAnalyzer()

        while not stop_event.is_set():
            #pint("\n[Background Thread] Working...")
            # Wait for 3 seconds, but check often if we need to stop
            time.sleep(3)
            ## doji
            ta.show_doji()
            ## Vix
            ta.vix_elevated()
            ## check moving average
            ta.check_with_ema()
            ## check if I should sell for profit
            ## check if I should sell for stop loss

        print("[Background Thread] Stopped.")
   
    def run(self):
        print("Trading agent started")

        ## first collect stock info and save in class

        '''
        if not os.path.isfile('scan_results.csv'):
            print("No existing scan results found. Running new scan.")
            update_ticker_csv()

        df = pd.read_csv('scan_results.csv')
        print("Trading agent completed, num of ticker: " + str(len(df)))

        '''

        stop_event = threading.Event()

        # Start the background thread
        t = threading.Thread(target=self.background_task, args=(stop_event,), daemon=True)
        t.start()

        print("Main loop started. Type 'quit' to quit.")

        # Main input loop
        while True:
            user_input = input("Enter command: ").strip()

            if user_input.lower() == "quit":
                print("Exiting program...")
                stop_event.set()  # Tell the background thread to stop
                break
            else:
                print(f"You typed: {user_input}")
                self.interpret_trade_command(user_input)

        # Wait for the background thread to finish cleaning up
        t.join()


    def scan_tickers(self, exchanges=None, min_volume=1500000, min_close=5.0):
        exchanges = exchanges or ["NYSE", "NASDAQ"]
        print("Collecting NYSE/NASDAQ tickers with volume > 1,500,000 and close > 5")
        tickers_by_exchange = collect_all_exchange_tickers(
            exchanges=exchanges,
            min_volume=min_volume,
            min_close=min_close,
        )
        print("Collected tickers:")
        for exchange, tickers in tickers_by_exchange.items():
            print(f" {exchange}: {len(tickers)} tickers")
        return tickers_by_exchange

    @staticmethod
    def save_scan_results(tickers_by_exchange: Dict[str, List[str]], path: str = "scan_results.csv"):
        rows = []
        for tickers in tickers_by_exchange.values():
            for ticker in tickers:
                rows.append({"ticker": ticker})
        if rows:
            df = pd.DataFrame(rows)
            df.to_csv(path, index=False)
            print(f"Saved scan results to {path}")
        else:
            print("No tickers found; no scan results saved.")

    def update_ticker_csv(self, run_interval_hours: float = 24.0, output_path: str = "scan_results.csv"):
        print("Starting daily scan loop.")
        try:
            tickers_by_exchange = self.scan_tickers()
            self.save_scan_results(tickers_by_exchange, output_path)
        except KeyboardInterrupt:
            print("Update ticker csv stopped by user.")

    
    @classmethod
    def interpret_trade_command(cls, command: str) -> dict:
        """
        Parses an unstructured English phrase and converts it into a machine-readable 
        dictionary containing: action, quantity, symbol, and price.
        """
        # Normalize command to lowercase for clean matching
        clean_command = command.strip().lower()
        
        # Pattern looks for:
        # (?P<action>buy|sell)          -> Matches "buy" or "sell"
        # \s+(?P<quantity>\d+)          -> Matches one or more digits for share size
        # \s+(?P<symbol>[a-z0-9\.]+?)   -> Matches the ticker symbol (e.g., soxl, aapl, brk.b)
        # (\s+at\s+(?P<price>\d+(\.\d+)?))? -> Optional lookahead for "at X.XX" limit price
        pattern = r"(?P<action>buy|sell|stop)\s+(?P<quantity>\d+)\s+(?P<symbol>[a-z0-9\.]+?)(\s+at\s+(?P<price>\d+(\.\d+)?))?$"

        # Pattern for OCO order: "oco 100 soxl at 148 and 142"
        oco_pattern = r"(?P<action>oco)\s+(?P<quantity>\d+)\s+(?P<symbol>[a-z0-9\.]+?)\s+at\s+(?P<price>\d+(\.\d+)?)\s+and\s+(?P<stop_price>\d+(\.\d+)?)"   

        match = re.match(pattern, clean_command)
        if not match:
            match = re.match(oco_pattern, clean_command)
        if not match:
            print(f"Could not interpret phrase: '{command}'. Please use format 'buy [qty] [symbol] at [price]' or 'oco [qty] [symbol] at [price] and [stop_price]'.")
            return None

        data = match.groupdict()
        
        client = SchwabClient()
        if data["action"] == "oco":
            client.place_order(symbol=data['symbol'], quantity=int(data['quantity']), action="oco", price=float(data['price']), stop_price=float(data['stop_price']))
        elif data["action"] == "stop" or data["action"] == "sell" or data["action"] == "buy":
            client.place_order(symbol=data['symbol'], quantity=int(data['quantity']), action=data["action"], price=float(data['price']))
        return None                 


if __name__ == "__main__":
    import sys

    agent = TradingAgent()
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd in {"scan", "s"}:
            agent.scan_tickers()
        elif cmd in {"daily", "schedule", "run-daily"}:
            agent.update_ticker_csv()
        else:
            print("Unknown command. Use 'scan' or 'daily'.")
    else:
        agent.run()

        







