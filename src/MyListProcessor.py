import pandas as pd
import numpy as np
from technical_analyze import TechnicalAnalyzer
import time

RED = '\033[31m'
GREEN = '\033[32m'
YELLOW = '\033[33m'
BLUE = '\033[34m'
RESET = '\033[0m' # Resets the color back to default

class MyListProcessor:

    wait_list = None
    # when list has a price, that is a manual set price, just need to use that price
    # this apply to left side trade only
    # if no price present, use the default criteria
    my_positions = None
    wait_breakout = None

    _schwab_client = None  # Placeholder for SchwabClient instance
    _initialized = False
    _tech_analyzer = None

    def __init__(self):
        
        if MyListProcessor._initialized is True:
            print ("MyListProcessor already initialized")
            return None
        
        MyListProcessor.wait_list = pd.read_csv('src/wait_list.csv')
        MyListProcessor.my_positions = pd.read_csv('src/my_positions.csv')
        MyListProcessor._tech_analyzer = TechnicalAnalyzer()

        MyListProcessor._initialized = True

    def process_wait_list(self):

        for index, row in self.wait_list.iterrows():
            symbol = row['symbol']
            if symbol.startswith("^"):
                continue
            quote = self._tech_analyzer._schwab_client.get_quote(symbol)
            atr = self._tech_analyzer.stock_info.get(symbol, {}).get("atr").iloc[-1]
            cur_price =  quote[symbol.upper()]['quote']['lastPrice']
            ema50_val = self._tech_analyzer.stock_info.get(symbol, {}).get("ema50").iloc[-1][symbol.upper()] 
            ema100_val = self._tech_analyzer.stock_info.get(symbol, {}).get("ema100").iloc[-1][symbol.upper()] 

            if abs(float(row['price']) - cur_price)/atr < 0.2:
                print(f"{symbol} is at buy price {cur_price}")
            elif abs(cur_price - ema100_val)/atr < 0.2:
                print(f"{symbol} is at 100ema ({cur_price})")
            elif abs(cur_price - ema50_val)/atr < 0.2:
                print(f"{symbol} is at 50ema ({cur_price})")
                

    def process_my_position(self):
        #  sell criteria: remember your problem is that you do not sell, you should even it end up with 
        #                 empty hand.  Control drawdown is your first priority in your age.
        #  1: when stop limit price is specified
        #  2. when stock rise from bottome more than 20%
        #  3. Have a subbden drop of > 4%, this must be closed at the end of the day, as long 
        #     as if it does not bounce back to yesterday's mid price
        #  4. 10 ema bend down
        #  5. your loss is > 4%

        for index, row in self.my_positions.iterrows():
            symbol = row['symbol']
            stop = row['stop']
            cost = row['cost']
            target = row['target']
            quote = self._tech_analyzer._schwab_client.get_quote(symbol)
            last_price =  quote[symbol.upper()]['quote']['lastPrice'] 
            atr = self._tech_analyzer.stock_info.get(symbol, {}).get("atr").iloc[-1]
            need_sell  = False
            if not pd.isna(stop) and last_price <= float(stop):
                # 1
                print(RED + f"{symbol} is below stop limit {stop}, sell NOW!!")
                need_sell = True
            elif not pd.isna(target) and last_price >= float(target):
                    print(RED + f"{symbol} has reached target {target}, sell NOW!!")
                    need_sell = True
            else:
                history = self._tech_analyzer.stock_info.get(symbol, {}).get("history")
                prev_close = history["Close"].iloc[-1][symbol.upper()]
                ema10_val1 = self._tech_analyzer.stock_info.get(symbol, {}).get("ema10").iloc[-1][symbol.upper()] 
                ema10_val2 = self._tech_analyzer.stock_info.get(symbol, {}).get("ema10").iloc[-3][symbol.upper()] 

                rised = self._tech_analyzer.check_rising_price(history, 25)
                text = ""
                # 2
                if rised['is_rising'] and rised['percent_change'] > 30:
                    text += "rised over 30%; "
                    need_sell = True
                #3.
                if last_price < prev_close * 0.96:  
                    text += " is having s sudden drop"
                    need_sell = True
                #4 
                if  ema10_val1 < ema10_val2:
                    text += "ema10 bending downward "
                if not pd.isna(cost):
                    if (float(cost) - last_price)/last_price > 0.04:
                        text += "loss is more than 4%"
                        need_sell = True

                if text is not "":
                    print(RED + f"{symbol}: {text}")

            if need_sell:
                self._tech_analyzer.speak(f"Sell {symbol.upper()}")

        print(RESET + "\n")

if __name__ == "__main__":
    ml = MyListProcessor()
    ml.process_wait_list()
    ml.process_my_position()
