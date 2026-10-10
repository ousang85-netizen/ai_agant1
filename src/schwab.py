"""Placeholder utilities for interacting with a Schwab brokerage account."""

from typing import Dict, List
from time import sleep
from xmlrpc import client
import schwabdev
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo
import httpx

appKey = "JaXlHdgKQCgGB4SLefipOmmtRkIhhTlQTKJAfLhjG8e7VMi4"
appSecret = "mCtrPqOA8xlbPgf4T6PjFPUNxtNkUct3JY5ZgSpZQ4IZOnC4C3S7BmNreUPkAZ6a" 
callbackUrl = "https://127.0.0.1"


try:
    from .constants import (
        DEFAULT_BUTTERFLY_LEG_INTERVAL,
        DEFAULT_OPTION_CHAIN_INTERVAL,
        DEFAULT_SPREAD_LEG_INTERVAL,
        EXCLUDED_HOLDING_TICKERS,
        MAX_CREDIT_SPREAD_PRICE,
        MAX_EQUITY_ORDER_VALUE,
        MARKET_CLOSE_TIME,
        MIN_CREDIT_SPREAD_PRICE,
        NEW_YORK_TIMEZONE,
        OPTION_CHAIN_STRIKE_COUNT,
        OPTION_CONTRACT_MULTIPLIER,
        OPTION_PRICE_SCALE,
        PACIFIC_TIMEZONE,
        SCHWAB_TIMEOUT_SECONDS,
        SPX_SYMBOL,
        SPXW_OPTION_PREFIX,
        STOP_LIMIT_MULTIPLIER,
        TAKE_PROFIT_MULTIPLIER,
        UTC_TIMEZONE,
        VIX_SYMBOL,
    )
    from .order_manager import OrderManager
except ImportError:
    from constants import (
        DEFAULT_BUTTERFLY_LEG_INTERVAL,
        DEFAULT_OPTION_CHAIN_INTERVAL,
        DEFAULT_SPREAD_LEG_INTERVAL,
        EXCLUDED_HOLDING_TICKERS,
        MAX_CREDIT_SPREAD_PRICE,
        MAX_EQUITY_ORDER_VALUE,
        MARKET_CLOSE_TIME,
        MIN_CREDIT_SPREAD_PRICE,
        NEW_YORK_TIMEZONE,
        OPTION_CHAIN_STRIKE_COUNT,
        OPTION_CONTRACT_MULTIPLIER,
        OPTION_PRICE_SCALE,
        PACIFIC_TIMEZONE,
        SCHWAB_TIMEOUT_SECONDS,
        SPX_SYMBOL,
        SPXW_OPTION_PREFIX,
        STOP_LIMIT_MULTIPLIER,
        TAKE_PROFIT_MULTIPLIER,
        UTC_TIMEZONE,
        VIX_SYMBOL,
    )
    from order_manager import OrderManager

from yfinance import data

class SchwabClient:
    _instance = None
    _initialized = False
    _client = None
    _account_hash = None
    _orders = []
    _order_manager = None


    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            #cls._instance = super(SchwabClient, cls).__new__(cls)
            cls._instance = super().__new__(cls)
            cls._client = schwabdev.Client(
                appKey, appSecret,  callbackUrl, timeout=SCHWAB_TIMEOUT_SECONDS,
            )
            linked_accounts = cls._client.linked_accounts().json()
            cls._account_hash = linked_accounts[0].get('hashValue') # this will get the first linked account

        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._initialized = True    
            self._order_manager = OrderManager(self)

    def start_order_monitor_thread(self):
        self._order_manager.start_monitor_thread()

    def stop_order_monitor_thread(self):
        self._order_manager.stop()

    def convert_pacific_to_schwab(date_str: str) -> tuple[str, int]:

        #. Attach the Pacific timezone (handles PST/PDT transitions automatically)
        pacific_aware = date_str.replace(tzinfo=PACIFIC_TIMEZONE)
        
        return pacific_aware.astimezone(UTC_TIMEZONE)

    @staticmethod
    def ToPacificTime(schwab_time:str):
        utc_dt_rest = datetime.fromisoformat(schwab_time.replace("Z", "+00:00")) 
        pacific_dt_rest = utc_dt_rest.astimezone(PACIFIC_TIMEZONE)

        return pacific_dt_rest.strftime("%Y-%m-%d %H:%M:%S %Z")

    @staticmethod
    def report_unpaired_order(order):
        exec_time = SchwabClient.ToPacificTime(order["enteredTime"])
        profit = 0.
        report = ""

        report += f"{exec_time}->None; "
        legs = SchwabClient.compose_leg_info(order)

        for id in range(len(legs)):
            report += OrderManager.convert_option_ticker(legs[id]['symbol'])
            report += "; "
            if legs[id]['instruction'].startswith("BUY"):
                profit -= legs[id]['price'] * legs[id]['quantity']
            elif legs[id]['instruction'].startswith("SELL"):
                profit += legs[id]['price'] * legs[id]['quantity']
            else:
                print(f"Unexpetced instruction : {legs[id]['instruction']}")
                return None

        profit *= 100
        report += f"profit:{profit:.2f}"
        return {"report": report, "profit":profit}

    @staticmethod
    def compose_leg_info(order):
        order_legs = order.get("orderLegCollection")
        legs = []
        for order_leg in order_legs:
            leg = {}
            leg['legId'] = order_leg['legId']
            leg["time"] = SchwabClient.ToPacificTime(order.get("enteredTime"))
            leg["symbol"] = order_leg.get('instrument').get('symbol')
            leg["instruction"] = order_leg["instruction"]
            leg["complexOrderStrategyType"] = order["complexOrderStrategyType"]
            leg['quantity'] = 0.
            leg['price'] = 0.
            legs.append(leg)

        for activity in order.get("orderActivityCollection", []):
            for execution in activity.get("executionLegs", []):
                legId = execution.get("legId", 1)
                leg =next((item for item in legs if item.get("legId") == legId), None)
                if leg['quantity'] == 0:
                    leg['quantity'] = float(execution["quantity"])
                    leg['price'] = float(execution["price"])
                else:
                    leg['price'] = ((leg['quantity'] * leg['price']) + (float(execution["quantity"]) *  float(execution["price"])))\
                          / (leg['quantity'] + execution["quantity"])
                    leg['quantity'] += float(execution["quantity"])
        return legs

        '''
        legs = [] #[None] * len(order['orderLegCollection'])
        ordor_legs = order["orderLegCollection"]
        exec_legs = order["orderActivityCollection"][0]["executionLegs"]

        for id in range(len(order['orderLegCollection'])):
            leg = {}
            key = id+1
            cur_order_leg =next((item for item in ordor_legs if item.get("legId") == key), None)
            cur_exec_leg = next((item for item in exec_legs if item.get("legId") == key), None)

            leg["time"] = SchwabClient.ToPacificTime(order["enteredTime"])
            leg["symbol"] = order["orderLegCollection"][id]['instrument']['symbol']
            leg["instruction"] = cur_order_leg["instruction"]
            leg["complexOrderStrategyType"] = order["complexOrderStrategyType"]
            leg["price"] = cur_exec_leg["price"]
            leg["quantity"] = cur_exec_leg["quantity"]
            if cur_exec_leg["quantity"] != cur_order_leg["quantity"]:
                print(f"Partial order found !!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            legs.append(leg)
        return legs  
        '''
    @staticmethod
    def compare_multi_leg_option_orders(buy_order: Dict, sell_order: Dict) -> Dict:
        """Compare matching buy and sell option orders and estimate their P&L.

        Prices are Schwab's net order prices per share, not execution fills.
        """
  
        # pre-check if two order are pair:
        if buy_order['complexOrderStrategyType'] != sell_order['complexOrderStrategyType']:
            return None
        if buy_order['complexOrderStrategyType'] == 'BUTTERFLY':
            print ("compare buterfly")
        #need to go through execution legs :
        if 'orderActivityCollection' in buy_order and 'executionLegs' in buy_order["orderActivityCollection"][0]:
            buy_legs = sorted(SchwabClient.compose_leg_info(buy_order), key = lambda x:x["symbol"])
            if buy_order.get("orderActivityCollection")[0]['executionType'] != 'FILL':
                print(f"buy order executon leg executeType is not FILL \
                        { buy_order.get("orderActivityCollection")[0]['executionType']}")
        else:
            print("Buy order do not have execution legs")
            return None
        
        if 'orderActivityCollection' in sell_order and 'executionLegs' in sell_order["orderActivityCollection"][0]:
            sell_legs = sorted(SchwabClient.compose_leg_info(sell_order), key = lambda x:x["symbol"])
            if sell_order.get("orderActivityCollection")[0]['executionType'] != 'FILL':
                print(f"sell order executon leg executeType is not FILL \
                        { sell_order.get("orderActivityCollection")[0]['executionType']}")
        else:
            print("Sell order do not have execution legs")
            return None

        if len(buy_legs)!= len(sell_legs):
            return None

        # collect symbol 
        profit = 0.
        buy_time = SchwabClient.ToPacificTime(buy_order["enteredTime"])
        sell_time = SchwabClient.ToPacificTime(sell_order["enteredTime"])
        report = f"{buy_time}->{sell_time}; "
        for id in range(len(buy_legs)):
            if buy_legs[id].keys() != sell_legs[id].keys():
                return None
            if buy_legs[id]['symbol'] != sell_legs[id]['symbol']:
                return None
            report += OrderManager.convert_option_ticker(buy_legs[id]['symbol'])
            report += ";"
            if buy_legs[id]['instruction'].startswith("BUY"):
                profit -= buy_legs[id]['price'] * buy_legs[id]['quantity']
            elif buy_legs[id]['instruction'].startswith("SELL"):
                profit += buy_legs[id]['price'] * buy_legs[id]['quantity']
            else:
                print(f"Unexpetced instruction : {buy_legs[id]['instruction']}")
                return None
            
            if sell_legs[id]['instruction'].startswith("BUY"):
                profit -= sell_legs[id]['price'] * sell_legs[id]['quantity']
            elif sell_legs[id]['instruction'].startswith("SELL"):
                profit += sell_legs[id]['price'] * sell_legs[id]['quantity']
            else:
                print(f"Unexpetced instruction : {sell_legs[id]['instruction']}")
                return None
        profit *= 100
        report += f"profit:{profit:.2f}"
        return {"report": report, "profit":profit}

    def get_linked_accounts(self) -> List[Dict]:
        """Return a list of linked Schwab accounts."""
        return self._client.linked_accounts().json()

    def get_account_holdings(self) -> Dict:
        """Return a list of positions for a specific Schwab account."""
        stocks = []
        options = []
        positions = self._client.account_details(self._account_hash, fields="positions").json()
        
        for position in  positions["securitiesAccount"]["positions"]:
            if position['instrument']['symbol'] not in EXCLUDED_HOLDING_TICKERS:
        
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



    def _record_accepted_order(
        self, response, order_id, order, symbol, quantity, action, price
    ):
        if response is not None and 200 <= response.status_code < 300 and order_id:
            self._order_manager.record_order(
                order_id, symbol, quantity, action, price, order
            )

    @staticmethod
    def _confirm_order(order):
        legs = ", ".join(
            f"{leg.get('instruction', 'ORDER')} {leg.get('quantity', '')} "
            f"{OrderManager.convert_option_ticker(leg.get('instrument', {}).get('symbol', 'UNKNOWN'))}"
            for leg in order.get("orderLegCollection", [])
        )
        order_type = order.get("orderType", order.get("orderStrategyType", "ORDER"))
        price = order.get("price", "market")
        print(f"Order to submit: {order_type}; {legs}; price={price}")
        return input("Submit this order? [y/N]: ").strip().casefold() in {"y", "yes"}

    def get_client(self):
        return self._client

    def get_hash_value(self):
        if self._account_hash is None:
            linked_accounts = self.get_linked_accounts()
            if linked_accounts:
                self._account_hash = linked_accounts[0].get('hashValue')  # Set the hashValue of the first linked account
        return self._account_hash

    @staticmethod
    def account_orders(status: str = None, days_before:int  = 0) -> List[Dict]:
        """Get all orders for the Schwab account."""
        end_dt = datetime.now()
        start_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if days_before != 0:
            end_et = start_dt - timedelta(days_before-1)
            start_dt = start_dt - timedelta(days_before)
        start_dt = SchwabClient.convert_pacific_to_schwab(start_dt)
        end_dt = SchwabClient.convert_pacific_to_schwab(end_dt)

        return SchwabClient._client.account_orders(SchwabClient._account_hash, start_dt, end_dt, None, status)  # Return all orders
    
    @staticmethod
    def get_quote(symbol: str) -> List[Dict]:
        """Get quotes for the specified symbols."""
        if symbol == '^VIX':
            updated_symbol = VIX_SYMBOL
        else:
            updated_symbol = symbol

        #return SchwabClient._client.quote(symbol_id=updated_symbol).json()

        try:
            # Make the quote request
            response = SchwabClient._client.quote(symbol_id=updated_symbol)
            
            # Check if the response was successful before parsing JSON
            if response.status_code != 200:
                print(f"Error status code received when getting quote for {updated_symbol}: {response.status_code}")

        except httpx.HTTPStatusError as e:
            print(f"HTTP error occurred when getting quote for {updated_symbol}: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            print(f"An unexpected error occurred when getting quote for {updated_symbol}: {e}")

        return response.json() if response and response.status_code == 200 else None

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
                f"Could not read last price for {symbol}"
            ) from error
        current_minute_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        for contractType in ["CALL", "PUT"]:
            response =  SchwabClient._client.option_chains( 
                    symbol=symbol, contractType = contractType,
                    strikeCount=OPTION_CHAIN_STRIKE_COUNT,  # Broad strike buffer to ensure all 3 legs are included
                    interval=DEFAULT_OPTION_CHAIN_INTERVAL,
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
                text = f"{current_minute_str};{val};{current_price};{item['symbol']};{item['bid']};{item['ask']};delta={item['delta']}"
                output.append(text)
        return output


    def get_butterfly_quote(self, underlying_symbol, contractType, lower_strike, mid_strike, upper_strike, expiration_date=None, \
                            chain_interval=DEFAULT_OPTION_CHAIN_INTERVAL, leg_interval=DEFAULT_BUTTERFLY_LEG_INTERVAL):
        """
        Calculates the aggregate quote for a Call Butterfly Spread using schwabdev.
        Structure: Long 1 Lower, Short 2 Mid, Long 1 Upper
        """
        # 1. Request the option chain for the specified expiration date
        if expiration_date is None:
            response =  SchwabClient._client.option_chains(
                symbol=underlying_symbol,
                contractType=contractType,
                strikeCount=OPTION_CHAIN_STRIKE_COUNT,  # Broad strike buffer to ensure all 3 legs are included
                interval = chain_interval,
                daysToExpiration = 0,
                strategy="SINGLE"
            )
        else:
            response =  SchwabClient._client.option_chains(
                symbol=underlying_symbol,
                contractType=contractType,
                strikeCount=OPTION_CHAIN_STRIKE_COUNT,  # Broad strike buffer to ensure all 3 legs are included
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

        if lower_strike is None:
            lower_strike = mid_strike - leg_interval
        if upper_strike is None:
            upper_strike = mid_strike + leg_interval
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
        max_loss = butterfly_mid * OPTION_CONTRACT_MULTIPLIER
        max_profit = (
            (float(mid_strike) - float(lower_strike)) * OPTION_CONTRACT_MULTIPLIER
            - butterfly_mid * OPTION_CONTRACT_MULTIPLIER
        )  # Max profit occurs if the underlying is at mid_strike at expiration
        print(f"--- {underlying_symbol} Call Butterfly ({lower_strike}/{mid_strike}/{upper_strike}) ---")
        if expiration_date:
            print(f"Expiration: {expiration_date.strftime('%Y-%m-%d')}")
        print(f"Leg 1 ({lower_strike} C) Ask: ${leg_lower['ask']} | Bid: ${leg_lower['bid']} | Delta: {leg_lower['delta']}")
        print(f"Leg 2 ({mid_strike} C x2) Ask: ${leg_mid['ask']} | Bid: ${leg_mid['bid']} | Delta: {leg_mid['delta']}")
        print(f"Leg 3 ({upper_strike} C) Ask: ${leg_upper['ask']} | Bid: ${leg_upper['bid']} | Delta: {leg_upper['delta']}")
        print("--------------------------------------------------")
        print(f"butterfly Net Bid:   ${butterfly_bid:.2f}")
        print(f"butterfly Net Ask:   ${butterfly_ask:.2f}")
        print(f"butterfly Net Mid:   ${butterfly_mid:.2f} (Estimated Entry Cost {max_loss:.2f})")
        print(f"butterfly max profit:   ${max_profit:.2f}")
        return {"butterfly_mid": butterfly_mid, "max_loss": max_loss, "max_profit": max_profit,
                "leg_lower": leg_lower, "leg_mid": leg_mid, "leg_upper": leg_upper}

    def get_spread_quote(self, underlying_symbol, contractType, sell_strike, buy_strike=None, expiration_date=None, chain_interval=DEFAULT_OPTION_CHAIN_INTERVAL, leg_interval=DEFAULT_SPREAD_LEG_INTERVAL):
        """
        Calculates the aggregate quote for a Call Butterfly Spread using schwabdev.
        Structure: Long 1 Lower, Short 2 Mid, Long 1 Upper
        """
        # 1. Request the option chain for the specified expiration date
        if expiration_date is None:
            response =  SchwabClient._client.option_chains(
                symbol=underlying_symbol,
                contractType=contractType,
                strikeCount=OPTION_CHAIN_STRIKE_COUNT,  # Broad strike buffer to ensure all 3 legs are included
                interval = chain_interval,
                daysToExpiration = 0,
                strategy="SINGLE"
            )
        else:
            response =  SchwabClient._client.option_chains(
                symbol=underlying_symbol,
                contractType=contractType,
                strikeCount=OPTION_CHAIN_STRIKE_COUNT,  # Broad strike buffer to ensure all 3 legs are included
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
        max_loss = (
            abs(float(buy_strike) - float(sell_strike)) - spread_mid
        ) * OPTION_CONTRACT_MULTIPLIER  # Max loss occurs if the underlying is at or below sell_strike at expiration
        max_profit = spread_mid * OPTION_CONTRACT_MULTIPLIER  # Max profit occurs if the underlying is at or above buy_strike at expiration

        print(f"--- {underlying_symbol} Call Spread ({sell_strike}/{buy_strike}) ---")
        if expiration_date:
            print(f"Expiration: {expiration_date.strftime('%Y-%m-%d')}")
        else:
            print("Expiration: Nearest available")
        C_or_P = "C" if contractType.upper() == "CALL" else "P"
        print(f"Leg sell ({sell_strike} {C_or_P}) Ask: ${leg_sell['ask']} | Bid: ${leg_sell['bid']} | Delta: {leg_sell['delta']}")
        print(f"Leg buy ({buy_strike} {C_or_P}) Ask: ${leg_buy['ask']} | Bid: ${leg_buy['bid']} | Delta: {leg_buy['delta']}")
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

        fly_quote = self.get_butterfly_quote(
            underlying_symbol,
            contract_type,
            lower_strike,
            middle_strike,
            upper_strike,
            expiration_date=None,
            leg_interval=DEFAULT_BUTTERFLY_LEG_INTERVAL,
        )

        if (not fly_quote['leg_lower']['symbol'].startswith(SPXW_OPTION_PREFIX)) or \
           (not fly_quote['leg_mid']['symbol'].startswith(SPXW_OPTION_PREFIX)) or \
           (not fly_quote['leg_upper']['symbol'].startswith(SPXW_OPTION_PREFIX)) :
            if underlying_symbol == SPX_SYMBOL:
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
        price = round(price * OPTION_PRICE_SCALE) / OPTION_PRICE_SCALE
        order = {
            "orderType": "NET_DEBIT " if order_action == "BUY" else "NET_CREDIT",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "complexOrderStrategyType": "BUTTERFLY",
            "price": f"{price:.2f}",
            "orderLegCollection": legs,
        }

        if not self._confirm_order(order):
            print("Order not submitted.")
            return None, None
        response = self._client.place_order(self._account_hash, order)
        order_id = None
        if 200 <= response.status_code < 300:
            order_id = response.headers.get("location", "/").split("/")[-1]
            if order_id:
                self._orders.append(order_id)
                self._record_accepted_order(
                    response, order_id, order, underlying_symbol, quantity,
                    order_action, price
                )
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
            market_now = datetime.now(NEW_YORK_TIMEZONE)
            expiration_date = market_now.date()
            if market_now.weekday() >= 5 or market_now.time() >= MARKET_CLOSE_TIME:
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
        option_quote = self.get_spread_quote(
            underlying_symbol,
            option_type,
            sell_strike,
            buy_strike,
            expiration_date=expiration_date,
            chain_interval=DEFAULT_OPTION_CHAIN_INTERVAL,
            leg_interval=leg_interval,
        )
 
        #return {"spread_mid": spread_mid, "max_loss": max_loss, "max_profit": max_profit,
        #        "leg_nearer": leg_nearer, "leg_farther": leg_farther}
        price = option_quote['spread_mid']
        if price <= 0:
            raise ValueError("Spread mid price must be positive for a credit spread")
        if (not option_quote['leg_sell']['symbol'].startswith(SPXW_OPTION_PREFIX)) or \
           (not option_quote['leg_buy']['symbol'].startswith(SPXW_OPTION_PREFIX)):
            if underlying_symbol == SPX_SYMBOL:
                raise ValueError("spx option symbol {option_quote['leg_sell']['symbol']} is not right")
            
        price = round(price * OPTION_PRICE_SCALE) / OPTION_PRICE_SCALE
        if price > MAX_CREDIT_SPREAD_PRICE:
            print(
                f"credit spread price ({price}) is over current limit of "
                f"{MAX_CREDIT_SPREAD_PRICE}"
            )
            return None, None
        if price < MIN_CREDIT_SPREAD_PRICE:
            print(
                f"credit spread price ({price}) is below current limit of "
                f"{MIN_CREDIT_SPREAD_PRICE}"
            )
            return None, None
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
        opposite_legs = [
            {
                "instruction": instruction,
                "quantity": str(quantity),
                "instrument": {
                    "symbol": option_symbol,
                    "assetType": "OPTION",
                },
            }
            for instruction, option_symbol in (
                ("BUY_TO_CLOSE", option_quote['leg_sell']['symbol']),
                ("SELL_TO_CLOSE", option_quote['leg_buy']['symbol']),
            )
        ]
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
                "orderStrategyType": "OCO",

                "childOrderStrategies": [
                    {
                    "orderStrategyType": "SINGLE",
                    "orderType": "NET_DEBIT",
                    "session": "NORMAL",
                    "duration": "DAY",
                    "complexOrderStrategyType": "VERTICAL",
                    "price": f"{(price+2.):.2f}",
                    "orderLegCollection": opposite_legs,
                    },

                    {
                    "orderStrategyType": "SINGLE",
                    "orderType": "STOP",
                    "session": "NORMAL",
                    "duration": "DAY",
                    "complexOrderStrategyType": "VERTICAL",
                    #"price": f"{(price+0.8):.2f}",
                    "stopPrice": f"{(price+0.8):.2f}",
                    "orderLegCollection": opposite_legs,
                    }
                ]        
                }
            ]
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

        if not self._confirm_order(order):
            print("Order not submitted.")
            return None, None 
        response = self._client.place_order(self._account_hash, order)
        order_id = None
        if 200 <= response.status_code < 300:
            order_id = response.headers.get("location", "/").split("/")[-1]
            if order_id:
                self._orders.append(order_id)
                self._record_accepted_order(
                    response, order_id, order, underlying_symbol, quantity,
                    "SELL", price
                )
        return response, order_id

    def place_order(self, symbol: str, quantity: int,  action: str = "BUY", price: float = None, stop_price: float = None):
        """Compose an order for a specific Schwab account."""

        """Limit the total money spent on this order to the configured value."""
        if price * quantity > MAX_EQUITY_ORDER_VALUE:
            print(
                f"Order exceeds ${MAX_EQUITY_ORDER_VALUE} limit: "
                f"{price * quantity}"
            )
            return None

        if action == "buy":
            sell_limit = "{:.2f}".format(price * TAKE_PROFIT_MULTIPLIER)
            stop_limit = "{:.2f}".format(price * STOP_LIMIT_MULTIPLIER)
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


        if not self._confirm_order(order):
            print("Order not submitted.")
            return None, None
        response = self._client.place_order(self._account_hash, order)  # Return the order response
        order_id = None
        if response.status_code >= 200 and response.status_code < 300:
            print(f"Order placed successfully: response.status_code = {response.status_code}")
            order_id = response.headers.get('location', '/').split('/')[-1]
            if order_id:
                self._orders.append(order_id)
                self._record_accepted_order(
                    response, order_id, order, symbol, quantity, action, price
                )
        else:
            print(f"Failed to place order: response.status_code = {response.status_code}")
        return response, order_id

    @staticmethod
    def genetate_intrday_spx_trade_report(days_before: int = 0):
        all = SchwabClient.account_orders(days_before = days_before).json()
        if all is None:
            print("failed to account_orders")
        buy_orders = []
        sell_orders = []
        others = []
        reports = []
        remains = []
        for order in all:

            if order['status'] in ['REJECTED', 'CANCELED', 'EXPIRED', 'REPLACED']:
                continue
            if order['status'] not in  ['FILLED', 'REPLACED']:
                print(f"ORDER STATUS not expected: {order['status']}")
            if 'orderLegCollection' in order:
                symbol = order['orderLegCollection'][0]['instrument']['symbol']
                if not symbol.startswith(SPXW_OPTION_PREFIX):
                    print(f"{symbol} is not start with {SPXW_OPTION_PREFIX}!!")
                    continue
                if order['orderLegCollection'][0]['instruction'].startswith('BUY'):
                    buy_orders.append(order)
                elif order['orderLegCollection'][0]['instruction'].startswith('SELL'):
                    sell_orders.append(order)
                else:
                    others.append(order)
                    print(f"OrderType {symbol}, {order['orderType']} is NOT credit or debit")
        total = 0.
        for buy_order in buy_orders:
            found = False
            to_remove = None
            for sell_order in sell_orders:
                res = SchwabClient.compare_multi_leg_option_orders(buy_order, sell_order)
                if res != None:
                    to_remove = sell_order
                    reports.append(res["report"])
                    total += res["profit"]
                    found = True
                    break
            if not found:
                remains.append(buy_order)
            else:
                sell_orders.remove(to_remove)

        for x in remains:
            res = SchwabClient.report_unpaired_order(x)
            reports.append(res["report"])
            total += res["profit"]

        for x in sell_orders:
            res = SchwabClient.report_unpaired_order(x)
            reports.append(res["report"])
            total += res["profit"]

        if others:
            print("There are unknown order type, neither buy nor sell")


        print("=" * 30)
        for report in reports:
            print(report)
        print("-" * 30)
        print(f"Total: {total:.2f}")

if __name__ == "__main__":

    import argparse

    days_before = 0
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--days", type=int, default=None, help="Number of days")
    args = parser.parse_args()

    if args.days is not None:
        days_before = int(args.days)

    print (f"days: {days_before}")

    client = SchwabClient()
    client.get_option_chain_data_list(SPX_SYMBOL)
    #a = client.order_details()  # Get details of the last order placed
    SchwabClient.genetate_intrday_spx_trade_report(days_before)


    #to-do:
    # trade analyze

    '''
    client.place_butterfly_order(
        underlying_symbol = SPX_SYMBOL,
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

    #client.get_option_chain_data_list(SPX_SYMBOL)
    '''
    client.get_butterfly_quote(SPX_SYMBOL, "CALL", 7645, 7655, 7665)

    client.place_butterfly_order(
        underlying_symbol = SPX_SYMBOL,
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
    client.get_spread_quote(
        SPX_SYMBOL,
        "CALL",
        7670,
        None,
        expiration_date=None,
        leg_interval=DEFAULT_SPREAD_LEG_INTERVAL,
    )
    '''
    #response, order_id = client.place_credit_spread_order(underlying_symbol = SPX_SYMBOL, expiration_date = None, \
    #                                            sell_strike = 7620, \
    #                                            leg_interval = DEFAULT_SPREAD_LEG_INTERVAL, quantity = 1)
    
