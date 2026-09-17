"""Entry point for the stock trading AI agent."""

# This file has been cleared as requested. Fill in trading logic here.

import threading
from typing import Dict, Any, List
from xmlrpc import client
import pandas as pd
import time
import os
import re
from datetime import date, datetime, timedelta
#pip install pyfiglet
#import pyfiglet
from print_chinese import print_big_chinese, print_highlight_chinese

#import data
from schwab import SchwabClient
#from src import data
from ticker_scanner import collect_all_exchange_tickers
from technical_analyze import TechnicalAnalyzer
from MyListProcessor import MyListProcessor
YELLOW = '\033[33m'
RESET = '\033[0m'

class TradingAgent:

    _ta = None
    def __init__(self):
        pass
        TradingAgent._ta = TechnicalAnalyzer()

    def background_task(self, stop_event):

        list_processor = MyListProcessor()
        scan_freq = 6
        stop_event.wait(timeout=2.0)
        while not stop_event.is_set():
            #pint("\n[Background Thread] Working...")
            # Wait for 3 seconds, but check often if we need to stop
            minutes = TradingAgent._ta.market_open_minute()
            #print(YELLOW + "               遵 守 交 易 纪 律" + RESET)
            #big_text = pyfiglet.figlet_format(" 遵 守 交 易 纪 律 ")
            #big_text = pyfiglet.figlet_format(" windows ")
            print_highlight_chinese("      遵 守 交 易 纪 律      \n      遵 守 交 易 纪 律      \n      遵 守 交 易 纪 律      ")

            if minutes < 0:
                print("Remember analyst SPY/QQQ, even stock at buy price, Indexes need to support to buy, stay away if Index intraday is downtrend")

            if minutes > 25 and minutes < 40:
                 self._ta.speak("Check for any chance to buy strong stock during price dip in the morning")

            if minutes > 120 and minutes < 180:
                print_highlight_chinese("TO-DO: CLOSE OUT ALL Holdings in schwab account.")
                self._ta.speak("CLOSE OUT ALL Holdings in schwab account.")

            if minutes > 360:
                print_highlight_chinese("TO-DO: 1. Check marekt sentiment, 2. Check Index/stock structure 3. If market is bearish, stay out")
                                        
            ## doji
            print("-" * 20 + " checking doji " + "-" * 20)
            self._ta.show_doji()
            ## Vix
            print("-" * 20 + " checking vix spike " + "-" * 20)
            self._ta.vix_elevated()

            ## check moving average
            print("-" * 20 + " checking if nearing ema " + "-" * 20)
            self._ta.check_with_ema()

            ## check rsi divergence
            ## check if I should sell for profit
            ## check if I should sell for stop loss
            print("-" * 20 + " checking my positions" + "-" * 20)
            list_processor.process_my_position()
            ## process wait_list.csv
            print("-" * 20 + " checking stocks reach to buy level " + "-" * 20)
            list_processor.process_wait_list()

            ## scan for big pool
            if --scan_freq  == 0:
                scan_freq = 6
                print("Perform scan task")
                ## check buy signal: macd crossover below 0; marvini;  reach support ema; 
                ## check reverse signal: 5ema break 10 ema, etc
            print(f"\n[Background Thread] Cycle complete. Waiting for next interval...")
            was_signaled = stop_event.wait(timeout=200)
            if was_signaled:
                break


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


        # Start the background thread
        stop_event = threading.Event()
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
                response = self.interpret_trade_command(user_input)
                if response != None and response.status_code >= 200 and response.status_code < 300:
                    print(f"command processes:{user_input}")

        # Wait for the background thread to finish cleaning up
        t.join(timeout=30.0)
        if t.is_alive():
            print("Background thread refused to exit in time. Forcing shutdown...") 


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

        minutes = TradingAgent._ta.market_open_minute()

                    
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


        # Now check for trade command
        match = re.match(pattern, clean_command) 
        if not match:
            match = re.match(oco_pattern, clean_command)
        if match:
            if minutes <= 5:
                print("Do not start trade yet, wait for 5min after open.")
                return None

            #print(f"Could not interpret phrase: '{command}'. Please use format 'buy [qty] [symbol] at [price]' or 'oco [qty] [symbol] at [price] and [stop_price]'.")
            #return None
            # match a order command
            data = match.groupdict()
        
            client = SchwabClient()
            if data["action"] == "oco":
                response, order_id = client.place_order(symbol=data['symbol'], quantity=int(data['quantity']), action="oco", price=float(data['price']), stop_price=float(data['stop_price']))
            elif data["action"] == "stop" or data["action"] == "sell" or data["action"] == "buy":
                response, order_id = client.place_order(symbol=data['symbol'], quantity=int(data['quantity']), action=data["action"], price=float(data['price']))

            if response != None and response.status_code >= 200 and response.status_code < 300:
                ## need to add order reason for it
                trade_reason = input("Trade reason: ").strip()
                with open("order_book.txt", "a", encoding="utf-8 ") as file:
                    file.write(f"{datetime.now()}: {clean_command};{order_id};[{trade_reason}]\n")
            return response

        # now check for get stock info command
        get_pattern = r"^get\s+(?P<metric>\w+)\s+of\s+(?P<symbol>\w+)$"
        match = re.match(get_pattern, clean_command)   
        if match:
            data = match.groupdict()
            if data["metric"] == "atr":
                atr = TradingAgent._ta.get_atr(data['symbol'])
                if atr != None:
                    print(f"{data["symbol"]}'s ATR = {atr}")
                else:
                    print(f"get {data["symbol"]} ATR error")      
                return None 
        #get fly call at 7590
        #get spread call at 7590
        pattern = r"^get\s+(?P<type>\w+)\s+(?P<callput>\w+)\s+at\s+(?P<value>\d+)$"
        match = re.match(pattern, clean_command)   
        if match:
            data = match.groupdict()
            client = SchwabClient()
            if data["type"] == "fly":
                v = float(data['value'])
                response = client.get_butterfly_quote(underlying_symbol='$SPX', contractType=data['callput'].upper(), mid_strike=v, lower_strike=v-10, upper_strike=v+10)
                if response != None and response.status_code >= 200 and response.status_code < 300:
                    #print(f"fly call at {data['value']} : {response.json()}")
                    pass
                else:
                    print(f"get fly data failed")      
                return None 
            elif data["type"] == "spread":
                v = float(data['value'])
                response = client.get_spread_quote(underlying_symbol='$SPX', contractType=data['callput'].upper(), nearer_strike=v, expiration_date=None, interval=5)
                if response != None and response.status_code >= 200 and response.status_code < 300:
                    #print(f"spread call at {data['value']} : {response.json()}")
                    pass
                else:
                    print(f"get spread data failed")      
                return None
            else:
                print(f"Unknown type: {data['type']}. Supported types are 'fly' and 'spread'.")
                return None

        print(f"Not yet support this command: {clean_command}")
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

        







