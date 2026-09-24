"""Placeholder utilities for interacting with a Schwab brokerage account."""

from typing import Dict, List
from time import sleep
from xmlrpc import client
import schwabdev
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from yfinance import data

appKey = "JaXlHdgKQCgGB4SLefipOmmtRkIhhTlQTKJAfLhjG8e7VMi4"
appSecret = "mCtrPqOA8xlbPgf4T6PjFPUNxtNkUct3JY5ZgSpZQ4IZOnC4C3S7BmNreUPkAZ6a" 
callbackUrl = "https://127.0.0.1"

class SchwabClient:
    _instance = None
    _initialized = False
    _client = None
    _account_hash = None
    _orders = []
    def get_linked_accounts(self) -> List[Dict]:
        """Return a list of linked Schwab accounts."""
        return self._client.linked_accounts().json()

    def get_account_holdings(self) -> Dict:
        """Return a list of positions for a specific Schwab account."""
        stocks = []
        options = []
        exclused_ticker= ['IMCC','ATNM','524ESC100', 'BRCHF', 'BTCS', 'WLDS', 'DDDX', 'CBDL', 
                'BLSP', '292693108', '137648101', '05581M503', 'RMHB']
 
        positions = self._client.account_details(self._account_hash, fields="positions").json()
        
        for position in  positions["securitiesAccount"]["positions"]:
            if position['instrument']['symbol'] not in exclused_ticker:
        
                temp = {}

                if position['instrument']['assetType'] == 'OPTION':
                    temp["symbol"] = position['instrument']['symbol']
                    temp["type"] = position['instrument']['putCall']
                    temp["contracts"] = position['longQuantity']
                    temp["description"] = position['instrument']['description']
                    options.append(temp)
                else:  #if position['instrument']['assetType'] == 'EQUITY':
                    temp["symbol"] = position['instrument']['symbol']
                    temp["shares"] = position['longQuantity']
                    stocks.append(temp)

        return {"stocks": stocks, "options": options}

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(SchwabClient, cls).__new__(cls)
            cls._client = schwabdev.Client(appKey, appSecret, callbackUrl)    
            linked_accounts = cls._client.linked_accounts().json()
            cls._account_hash = linked_accounts[0].get('hashValue') # this will get the first linked account

        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._initialized = True    

    def get_client(self):
        return self._client

    def get_hash_value(self):
        if self._account_hash is None:
            linked_accounts = self.get_linked_accounts()
            if linked_accounts:
                self._account_hash = linked_accounts[0].get('hashValue')  # Set the hashValue of the first linked account
        return self._account_hash

    @staticmethod
    def account_orders(status: str = None) -> List[Dict]:
        """Get all orders for the Schwab account."""
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=2)  # Last 1 year
        return SchwabClient._client.account_orders(SchwabClient._account_hash, start_dt, end_dt, None, status)  # Return all orders

    @staticmethod
    def get_quote(symbol: str) -> List[Dict]:
        """Get quotes for the specified symbols."""
        if symbol == '^VIX':
            return SchwabClient._client.quote(symbol_id='$VIX').json()

        return SchwabClient._client.quote(symbol_id=symbol).json()

    def order_details(self):
        """Get details of the last order placed."""
        if not self._orders:
            print("No orders have been placed yet.")
            return None
        for order_id in self._orders:
            print(f"Order ID: {order_id}")
            temp = self._client.order_details(self._account_hash, order_id)
            print(temp.json())

    def get_option_chain_data_list(self, symbol: str):

        output = []
        quote = self.get_quote(symbol)
        try:
            current_price = float(quote[symbol]["quote"]["lastPrice"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                f"Could not read last price for {underlying_symbol}"
            ) from error
        current_minute_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        for contractType in ["CALL", "PUT"]:
            response =  SchwabClient._client.option_chains( 
                    symbol=symbol, contractType = contractType,
                    strikeCount=100,  # Broad strike buffer to ensure all 3 legs are included
                    interval = 5,
                    daysToExpiration = 0,
                    strategy="SINGLE"
                )
            if response.status_code != 200:
                raise Exception(f"Failed to fetch option chain: {response.text}")
                
            chain_data = response.json()
            
            # Extract the map containing the call contracts
            if contractType == "CALL":
                callput_map = chain_data.get('callExpDateMap', {})
            else:
                callput_map = chain_data.get('putExpDateMap', {})
            
            # Schwab formats expiration keys by joining the date and days-to-expiry (e.g., "2026-10-16:40")
            date_key = None
            for key in callput_map.keys():
                date_key = key
                break

            if not date_key:
                raise ValueError(f"No option chain data found for expiration {expiration_date.strftime('%Y-%m-%d')}")
                
            expiry_chain = callput_map[date_key]
            for val in expiry_chain:
                item = expiry_chain[val][0]
                text = f"{current_minute_str};{val};{current_price};{item['symbol']};{item['bid']};{item['ask']}"
                output.append(text)
        return output


    def get_butterfly_quote(self, underlying_symbol, contractType, lower_strike, mid_strike, upper_strike, expiration_date=None, chain_interval=5, leg_interval=10):
        """
        Calculates the aggregate quote for a Call Butterfly Spread using schwabdev.
        Structure: Long 1 Lower, Short 2 Mid, Long 1 Upper
        """
        # 1. Request the option chain for the specified expiration date
        if expiration_date is None:
            response =  SchwabClient._client.option_chains(
                symbol=underlying_symbol,
                contractType=contractType,
                strikeCount=100,  # Broad strike buffer to ensure all 3 legs are included
                interval = chain_interval,
                daysToExpiration = 0,
                strategy="SINGLE"
            )
        else:
            response =  SchwabClient._client.option_chains(
                symbol=underlying_symbol,
                contractType=contractType,
                strikeCount=100,  # Broad strike buffer to ensure all 3 legs are included
                interval = chain_interval,
                fromDate=expiration_date.strftime("%Y-%m-%d"),
                toDate=expiration_date.strftime("%Y-%m-%d"),
                strategy="SINGLE"
            )
        if response.status_code != 200:
            raise Exception(f"Failed to fetch option chain: {response.text}")
            
        chain_data = response.json()
        
        # Extract the map containing the call contracts
        if contractType.upper() == "CALL":
            callput_map = chain_data.get('callExpDateMap', {})
        elif contractType.upper() == "PUT":
            callput_map = chain_data.get('putExpDateMap', {})
        else:
            raise ValueError(f"Invalid contract type: {contractType}. Must be 'CALL' or 'PUT'.")
        
        # Schwab formats expiration keys by joining the date and days-to-expiry (e.g., "2026-10-16:40")
        date_key = None
        for key in callput_map.keys():
            if expiration_date is None or key.startswith(expiration_date.strftime("%Y-%m-%d")):
                date_key = key
                break
                
        if not date_key:
            raise ValueError(f"No option chain data found for expiration {expiration_date.strftime('%Y-%m-%d')}")
            
        expiry_chain = callput_map[date_key]
        
        # 2. Isolate the specific legs
        try:
            # Schwab API uses string representation of floats for strike mapping (e.g., "150.0")
            leg_lower = expiry_chain[f"{float(lower_strike)}"][0] # Schwab wraps the strike contract payload in a list
            leg_mid = expiry_chain[f"{float(mid_strike)}"][0]
            leg_upper = expiry_chain[f"{float(upper_strike)}"][0]
        except KeyError as e:
            raise KeyError(f"One of the specified strikes was not found in the chain: {e}")

        # 3. Aggregate the pricing for a Long Call Butterfly
        # Formula for Net Debit Entry: Cost of Outer Legs - Credit of Inner Legs
        # Maximize what you pay (ask) and minimize what you receive (bid) for the net ask spread limit.
        butterfly_bid = leg_lower['bid'] + leg_upper['bid'] - (2 * leg_mid['ask'])
        butterfly_ask = leg_lower['ask'] + leg_upper['ask'] - (2 * leg_mid['bid'])
        butterfly_mid = (butterfly_bid + butterfly_ask) / 2
        max_loss =  butterfly_mid * 100 
        max_profit = (float(mid_strike) - float(lower_strike)) * 100 - butterfly_mid * 100  # Max profit occurs if the underlying is at mid_strike at expiration
        print(f"--- {underlying_symbol} Call Butterfly ({lower_strike}/{mid_strike}/{upper_strike}) ---")
        if expiration_date:
            print(f"Expiration: {expiration_date.strftime('%Y-%m-%d')}")
        print(f"Leg 1 ({lower_strike} C) Ask: ${leg_lower['ask']} | Bid: ${leg_lower['bid']}")
        print(f"Leg 2 ({mid_strike} C x2) Ask: ${leg_mid['ask']} | Bid: ${leg_mid['bid']}")
        print(f"Leg 3 ({upper_strike} C) Ask: ${leg_upper['ask']} | Bid: ${leg_upper['bid']}")
        print("--------------------------------------------------")
        print(f"butterfly Net Bid:   ${butterfly_bid:.2f}")
        print(f"butterfly Net Ask:   ${butterfly_ask:.2f}")
        print(f"butterfly Net Mid:   ${butterfly_mid:.2f} (Estimated Entry Cost {max_loss:.2f})")
        print(f"butterfly max profit:   ${max_profit:.2f}")
        return {"butterfly_mid": butterfly_mid, "max_loss": max_loss, "max_profit": max_profit,
                "leg_lower": leg_lower, "leg_mid": leg_mid, "leg_upper": leg_upper}

    def get_spread_quote(self, underlying_symbol, contractType, sell_strike, buy_strike = None, expiration_date=None, chain_interval=5, leg_interval=5):
        """
        Calculates the aggregate quote for a Call Butterfly Spread using schwabdev.
        Structure: Long 1 Lower, Short 2 Mid, Long 1 Upper
        """
        # 1. Request the option chain for the specified expiration date
        if expiration_date is None:
            response =  SchwabClient._client.option_chains(
                symbol=underlying_symbol,
                contractType=contractType,
                strikeCount=100,  # Broad strike buffer to ensure all 3 legs are included
                interval = chain_interval,
                daysToExpiration = 0,
                strategy="SINGLE"
            )
        else:
            response =  SchwabClient._client.option_chains(
                symbol=underlying_symbol,
                contractType=contractType,
                strikeCount=100,  # Broad strike buffer to ensure all 3 legs are included
                interval = chain_interval,
                fromDate=expiration_date.strftime("%Y-%m-%d"),
                toDate=expiration_date.strftime("%Y-%m-%d"),
                strategy="SINGLE"
            )
        if response.status_code != 200:
            raise Exception(f"Failed to fetch option chain: {response.text}")

        #data =self.get_quote(underlying_symbol)
        #current_price = data[underlying_symbol]['quote']['lastPrice']

        chain_data = response.json()
        
        # Extract the map containing the call contracts
        if contractType.upper() == "CALL":
            optiontype_map = chain_data.get('callExpDateMap', {})
        else:
            optiontype_map = chain_data.get('putExpDateMap', {})
        
        # Schwab formats expiration keys by joining the date and days-to-expiry (e.g., "2026-10-16:40")
        date_key = None
        for key in optiontype_map.keys():
            if expiration_date is None or key.startswith(expiration_date.strftime("%Y-%m-%d")):
                date_key = key
                break
                
        if not date_key:
            raise ValueError(f"No option chain data found for expiration {expiration_date.strftime('%Y-%m-%d')}")
            
        expiry_chain = optiontype_map[date_key]
        if buy_strike is None:
            quote = self.get_quote(underlying_symbol)
            try:
                current_price = float(quote[underlying_symbol]["quote"]["lastPrice"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(
                    f"Could not read last price for {underlying_symbol}"
                ) from error

            if current_price > sell_strike:
                buy_strike = sell_strike - leg_interval
            else:
                buy_strike = sell_strike + leg_interval
        
        # 2. Isolate the specific legs
        try:
            # Schwab API uses string representation of floats for strike mapping (e.g., "150.0")
            leg_sell = expiry_chain[f"{float(sell_strike)}"][0] # Schwab wraps the strike contract payload in a list
            leg_buy = expiry_chain[f"{float(buy_strike)}"][0] # Schwab wraps the strike contract payload in a list
        except KeyError as e:
            raise KeyError(f"One of the specified strikes was not found in the chain: {e}")

        # 3. Aggregate the pricing for a Long Call Butterfly
        # Formula for Net Debit Entry: Cost of Outer Legs - Credit of Inner Legs
        # Maximize what you pay (ask) and minimize what you receive (bid) for the net ask spread limit.
        spread_bid = leg_sell['bid'] - leg_buy['ask']
        spread_ask = leg_sell['ask'] - leg_buy['bid']
        spread_mid = (spread_bid + spread_ask) / 2
        max_loss = (abs(float(buy_strike) - float(sell_strike)) - spread_mid) * 100  # Max loss occurs if the underlying is at or below sell_strike at expiration
        max_profit = spread_mid * 100 # Max profit occurs if the underlying is at or above buy_strike at expiration

        print(f"--- {underlying_symbol} Call Spread ({sell_strike}/{buy_strike}) ---")
        if expiration_date:
            print(f"Expiration: {expiration_date.strftime('%Y-%m-%d')}")
        else:
            print("Expiration: Nearest available")
        print(f"Leg sell ({sell_strike} C) Ask: ${leg_sell['ask']} | Bid: ${leg_sell['bid']}")
        print(f"Leg buy ({buy_strike} C) Ask: ${leg_buy['ask']} | Bid: ${leg_buy['bid']}")
        print("--------------------------------------------------")
        print(f"Spread Net Bid:   ${spread_bid:.2f}")
        print(f"Spread Net Ask:   ${spread_ask:.2f}")
        print(f"Spread Net Mid:   ${spread_mid:.2f} (Estimated Entry Cost)")
        print(f"Max Loss:   ${max_loss:.2f}")
        print(f"Max Profit:   ${max_profit:.2f}")
        return {"spread_mid": spread_mid, "max_loss": max_loss, "max_profit": max_profit,
                "leg_sell": leg_sell, "leg_buy": leg_buy}

    def place_butterfly_order(
        self,
        underlying_symbol: str,
        expiration_date: date,
        lower_strike: float,
        middle_strike: float,
        upper_strike: float,
        quantity: int = 1,
        contract_type: str = None,
        price: float = None,
        action: str = "BUY",
    ):
        """Place a limit order for an opening call or put butterfly.

        A BUY butterfly is long one lower strike, short two middle strikes,
        and long one upper strike. SELL reverses those opening instructions.
        ``price`` is the net debit/credit per share, excluding the 100-share
        option multiplier.
        """
        if expiration_date is not None and not isinstance(expiration_date, date):
            raise TypeError("expiration_date must be a datetime.date")
        if not lower_strike < middle_strike < upper_strike:
            raise ValueError("strikes must be ordered lower < middle < upper")
        if quantity <= 0:
            raise ValueError("quantity must be positive")

        if contract_type is None:
            quote = self.get_quote(underlying_symbol)
            try:
                current_price = float(quote[underlying_symbol]["quote"]["lastPrice"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(
                    f"Could not read last price for {underlying_symbol}"
                ) from error
            if current_price >= middle_strike:
                contract_type = "PUT"
            else:
                contract_type = "CALL"
        else:
            contract_type = contract_type.upper()
            if contract_type not in {"CALL", "PUT"}:
                raise ValueError("action must be 'CALL' or 'PUT'")
            
        order_action = action.upper()
        if order_action not in {"BUY", "SELL"}:
            raise ValueError("action must be 'BUY' or 'SELL'")

        fly_quote = self.get_butterfly_quote(underlying_symbol, contract_type, lower_strike, middle_strike, upper_strike,expiration_date=None, leg_interval=10)

        if (not fly_quote['leg_lower']['symbol'].startswith('SPXW')) or \
           (not fly_quote['leg_mid']['symbol'].startswith('SPXW')) or \
           (not fly_quote['leg_upper']['symbol'].startswith('SPXW')) :
            if underlying_symbol == '$SPX':
                raise ValueError("spx option symbol {fly_quote['leg_lower']['symbol']} is not right")
            
        instructions = (
            ("BUY_TO_OPEN", "SELL_TO_OPEN", "BUY_TO_OPEN")
            if order_action == "BUY"
            else ("SELL_TO_OPEN", "BUY_TO_OPEN", "SELL_TO_OPEN")
        )
        symbols = [fly_quote['leg_lower']['symbol'], fly_quote['leg_mid']['symbol'], \
                   fly_quote['leg_upper']['symbol']]
        quantities = (quantity, quantity * 2, quantity)
        legs = [
            { 
                "instruction": instruction,
                "quantity": str(leg_quantity),
                "instrument": {
                    "symbol": symbol,
                    "assetType": "OPTION",
                },
            }
            for instruction, leg_quantity, symbol in zip(
                instructions, quantities, symbols
            )
        ]
        price = fly_quote['butterfly_mid']
        price = round(price*20)/20  # round to nearest 0.05
        order = {
            "orderType": "NET_DEBIT " if order_action == "BUY" else "NET_CREDIT",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "complexOrderStrategyType": "BUTTERFLY",
            "price": f"{price:.2f}",
            "orderLegCollection": legs,
        }

        response = self._client.place_order(self._account_hash, order)
        order_id = None
        if 200 <= response.status_code < 300:
            order_id = response.headers.get("location", "/").split("/")[-1]
            if order_id:
                self._orders.append(order_id)
        return response, order_id

    def place_credit_spread_order(
        self,
        underlying_symbol: str,
        expiration_date: Optional[date],
        sell_strike: float,
        leg_interval: float,
        quantity: int = 1,
        #price: float = None,
    ):
        """Place a limit order to open a call or put credit spread.

        A call credit spread sells the lower strike and buys the higher
        strike. A put credit spread sells the higher strike and buys the
        lower strike. ``sell_strike`` is the strike for the option being sold,
        and ``buy_strike`` is the strike for the option being bought.
        If the current price is above the sell strike, the method creates a put spread
        using ``sell_strike`` and ``buy_strike``. Otherwise it creates a
        call spread using ``sell_strike`` and ``buy_strike``.
        ``price`` is the net credit per share.
        """
        if expiration_date is not None and not isinstance(expiration_date, date):
            raise TypeError("expiration_date must be a datetime.date")
        if sell_strike <= 0:
            raise ValueError("sell_strike must be positive")
        if leg_interval <= 0:
            raise ValueError("leg_interval must be positive")
        if quantity <= 0:
            raise ValueError("quantity must be positive")

        if expiration_date is None:
            market_now = datetime.now(ZoneInfo("America/New_York"))
            expiration_date = market_now.date()
            if market_now.weekday() >= 5 or market_now.time() >= time(16, 0):
                expiration_date += timedelta(days=1)
                while expiration_date.weekday() >= 5:
                    expiration_date += timedelta(days=1)

        quote = self.get_quote(underlying_symbol)
        try:
            current_price = float(quote[underlying_symbol]["quote"]["lastPrice"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                f"Could not read last price for {underlying_symbol}"
            ) from error

        if current_price > sell_strike:
            buy_strike = sell_strike - leg_interval
            option_type = "PUT"
        else:
            buy_strike = sell_strike + leg_interval
            option_type = "CALL"

        # get option chain to verify that the strikes exist
        option_quote = self.get_spread_quote(underlying_symbol, option_type, sell_strike, buy_strike, \
                                             expiration_date=expiration_date, chain_interval=5, leg_interval=leg_interval)
 
        #return {"spread_mid": spread_mid, "max_loss": max_loss, "max_profit": max_profit,
        #        "leg_nearer": leg_nearer, "leg_farther": leg_farther}
        price = option_quote['spread_mid']
        if price <= 0:
            raise ValueError("Spread mid price must be positive for a credit spread")
        if (not option_quote['leg_sell']['symbol'].startswith('SPXW')) or \
           (not option_quote['leg_buy']['symbol'].startswith('SPXW')):
            if underlying_symbol == '$SPX':
                raise ValueError("spx option symbol {option_quote['leg_sell']['symbol']} is not right")
            
        price = round(price*20)/20  # round to nearest 0.05
        if price > 1.5:
            print("credit spread irce ({price}) is over current limit of 1.5")
            return None
        legs = [
            {
                "instruction": instruction,
                "quantity": str(quantity),
                "instrument": {
                    "symbol": option_symbol,
                    "assetType": "OPTION",
                },
            }
            for instruction, option_symbol in (
                ("SELL_TO_OPEN", option_quote['leg_sell']['symbol']),
                ("BUY_TO_OPEN", option_quote['leg_buy']['symbol']),
            )
        ]
        '''
        order = {
            "orderType": "NET_CREDIT",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "TRIGGER",
            "complexOrderStrategyType": "VERTICAL",
            "price": f"{price:.2f}",
            "orderLegCollection": legs,
            "childOrderStrategies": [
                {
                    "orderType": "STOP",
                    "session": "NORMAL",
                    "duration": "DAY",
                    "orderStrategyType": "SINGLE",
                    "complexOrderStrategyType": "VERTICAL",
                    "price": f"{price+0.6:.2f}",
                    "stopPrice": f"{price+0.8:.2f}",
                    "orderLegCollection": [
                        {
                            "instruction": "BUY_TO_CLOSE",
                            "quantity": str(quantity),
                            "instrument": legs[0]["instrument"],
                        },
                        {
                            "instruction": "SELL_TO_CLOSE",
                            "quantity": str(quantity),
                            "instrument": legs[1]["instrument"],
                        },
                    ],
                }
            ],
        }
        '''

        order = {
            "orderType": "NET_CREDIT",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            #"complexOrderStrategyType": "VERTICAL",
            "price": f"{price:.2f}",
            "orderLegCollection": legs,
        }
        
        response = self._client.place_order(self._account_hash, order)
        order_id = None
        if 200 <= response.status_code < 300:
            order_id = response.headers.get("location", "/").split("/")[-1]
            if order_id:
                self._orders.append(order_id)
        return response, order_id

    def place_order(self, symbol: str, quantity: int,  action: str = "BUY", price: float = None, stop_price: float = None):
        """Compose an order for a specific Schwab account."""

        """Limit the total money spend on this order to 10000"""
        if price * quantity > 10000:
            print(f"Order exceeds $10000 limit: {price * quantity}")
            return None

        if action == "buy":
            sell_limit = "{:.2f}".format(price * 1.05)  # Set sell limit to 5% above the buy price;
            stop_limit = "{:.2f}".format(price * 0.98);  # Set stop limit to 2% below the buy price;
            buy_order = {
                "orderType": "LIMIT",
                "session": "NORMAL",
                "duration": "DAY",
                "orderStrategyType": "TRIGGER",
                "price": str(price),
                "orderLegCollection": [
                    {"instruction": 'BUY',
                    "quantity": str(quantity),
                    "instrument": {"symbol": symbol,
                                    "assetType": "EQUITY",
                                    }
                    }
                ],
                "childOrderStrategies": [
                {
                        "orderStrategyType": "OCO",
                        "childOrderStrategies": [
                            {
                                "orderStrategyType": "SINGLE",
                                "session": "NORMAL",
                                "duration": "GOOD_TILL_CANCEL",
                                "orderType": "LIMIT",
                                "price": str(sell_limit),
                                "orderLegCollection": [
                                    {
                                        "instruction": "SELL",
                                        "quantity": str(quantity),
                                        "instrument": {
                                            "assetType": "EQUITY",
                                            "symbol": symbol,
                                        },
                                    }
                                ],
                            },
                            {
                                "orderStrategyType": "SINGLE",
                                "session": "NORMAL",
                                "duration": "GOOD_TILL_CANCEL",
                                "orderType": "STOP",
                                "stopPrice": str(stop_limit),
                                "orderLegCollection": [
                                    {
                                        "instruction": "SELL",
                                        "quantity":  str(quantity),
                                        "instrument": {
                                            "assetType": "EQUITY",
                                            "symbol": symbol,
                                        },
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
            order = buy_order
        elif action == "sell":
            sell_order = {
                "orderType": "LIMIT",
                "session": "NORMAL",
                "duration": "DAY",
                "orderStrategyType": "SINGLE",
                "price": str(price),
                "orderLegCollection": [
                    {
                        "instruction": "SELL",
                        "quantity": str(quantity),
                        "instrument": {
                            "symbol": symbol,
                            "assetType": "EQUITY",
                        },
                    }
                ],
            }
            order = sell_order
        elif action == "stop":
            stop_order = {
                "orderType": "STOP_LIMIT",
                "session": "NORMAL",
                "duration": "DAY",
                "orderStrategyType": "SINGLE",
                "price": str(price*.99),
                "stopPrice": str(price),
                "orderLegCollection": [
                    {
                        "instruction": "SELL",
                        "quantity": str(quantity),
                        "instrument": {
                            "symbol": symbol,
                            "assetType": "EQUITY",
                        },
                    }
                ],
            }
            order = stop_order  
        elif action == "oco":
            oco_order = {
                "orderStrategyType": "OCO",
                "childOrderStrategies": [
                    {
                        "orderStrategyType": "SINGLE",
                        "session": "NORMAL",
                        "duration": "GOOD_TILL_CANCEL",
                        "orderType": "LIMIT",
                        "price": str(price),
                        "orderLegCollection": [
                            {
                                "instruction": "SELL",
                                "quantity": str(quantity),
                                "instrument": {
                                    "assetType": "EQUITY",
                                    "symbol": symbol,
                                },
                            }
                        ],
                    },
                    {
                        "orderStrategyType": "SINGLE",
                        "session": "NORMAL",
                        "duration": "GOOD_TILL_CANCEL",
                        "orderType": "STOP",
                        "stopPrice": str(stop_price),
                        "orderLegCollection": [
                            {
                                "instruction": "SELL",
                                "quantity":  str(quantity),
                                "instrument": {
                                    "assetType": "EQUITY",
                                    "symbol": symbol,
                                },
                            }
                        ],
                    },
                ],
            }
            order = oco_order
        else:
            print(f"Invalid action: {action}. Must be 'buy', 'sell', 'stop', or 'oco'.")
            return None 


        response = self._client.place_order(self._account_hash, order)  # Return the order response
        order_id = None
        if response.status_code >= 200 and response.status_code < 300:
            print(f"Order placed successfully: response.status_code = {response.status_code}")
            order_id = response.headers.get('location', '/').split('/')[-1]
            if order_id:
                self._orders.append(order_id)
        else:
            print(f"Failed to place order: response.status_code = {response.status_code}")
        return response, order_id

if __name__ == "__main__":
    client = SchwabClient()
    a = client.order_details()  # Get details of the last order placed
    all=SchwabClient.account_orders().json()
    for order in all:
        if 'orderLegCollection' in order:
            print(order['orderLegCollection'][0]['instrument']['symbol'])

    '''
    holdings = client.get_account_holdings()    
    print("\nStock Holdings:")
    for holding in holdings["stocks"]   :
        print(holding)

    print("\nOption Holdings:")
    for holding in holdings["options"]:
        print(holding)      

    #client.place_order(symbol="IONX", quantity=100, action="BUY", price=31.48)
    client.order_details()  # Get details of the last order placed
    all=SchwabClient.account_orders().json()
    for order in all:
        if 'orderLegCollection' in order:
            print(order['orderLegCollection'][0]['instrument']['symbol'])
    '''
    #client.get_butterfly_quote('SPX', datetime.now(), 7655, 7645, 7665)

    client.get_option_chain_data_list('$SPX')
    '''
    client.get_butterfly_quote('$SPX', "CALL",7645, 7655, 7665) 

    client.place_butterfly_order(
        underlying_symbol = "$SPX",
        expiration_date = None,
        lower_strike = 7645,
        middle_strike = 7655,
        upper_strike = 7665,
        quantity = 1,
        contract_type = None,
        price = None,
        action = "SELL",
    )
    '''
    '''
    client.get_spread_quote('$SPX', "CALL", 7670, None, expiration_date=None, leginterval=5)
    response, order_id = client.place_credit_spread_order(underlying_symbol = '$SPX', expiration_date = None, \
                                                sell_strike = 7610, \
                                                leg_interval = 5, quantity = 1)
    '''
