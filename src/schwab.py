"""Placeholder utilities for interacting with a Schwab brokerage account."""

from typing import Dict, List
from time import sleep
from xmlrpc import client
import schwabdev
from datetime import date, datetime, timedelta

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

    def get_butterfly_quote(self, underlying_symbol, contractType, mid_strike, lower_strike, upper_strike,expiration_date=None, interval=5):
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
                interval = interval,
                daysToExpiration = 0,
                strategy="SINGLE"
            )
        else:
            response =  SchwabClient._client.option_chains(
                symbol=underlying_symbol,
                contractType=contractType,
                strikeCount=100,  # Broad strike buffer to ensure all 3 legs are included
                interval = interval,
                fromDate=expiration_date.strftime("%Y-%m-%d"),
                toDate=expiration_date.strftime("%Y-%m-%d"),
                strategy="SINGLE"
            )
        if response.status_code != 200:
            raise Exception(f"Failed to fetch option chain: {response.text}")
            
        chain_data = response.json()
        
        # Extract the map containing the call contracts
        if contractType.upper() == "CALL":
            call_map = chain_data.get('callExpDateMap', {})
        elif contractType.upper() == "PUT":
            call_map = chain_data.get('putExpDateMap', {})
        else:
            raise ValueError(f"Invalid contract type: {contractType}. Must be 'CALL' or 'PUT'.")
        
        # Schwab formats expiration keys by joining the date and days-to-expiry (e.g., "2026-10-16:40")
        date_key = None
        for key in call_map.keys():
            if expiration_date is None or key.startswith(expiration_date.strftime("%Y-%m-%d")):
                date_key = key
                break
                
        if not date_key:
            raise ValueError(f"No option chain data found for expiration {expiration_date.strftime('%Y-%m-%d')}")
            
        expiry_chain = call_map[date_key]
        
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
        max_profit = (float(mid_strike) - float(lower_strike)) * 100 - butterfly_mid  # Max profit occurs if the underlying is at mid_strike at expiration
        print(f"--- {underlying_symbol} Call Butterfly ({lower_strike}/{mid_strike}/{upper_strike}) ---")
        if expiration_date:
            print(f"Expiration: {expiration_date.strftime('%Y-%m-%d')}")
        print(f"Leg 1 ({lower_strike} C) Ask: ${leg_lower['ask']} | Bid: ${leg_lower['bid']}")
        print(f"Leg 2 ({mid_strike} C x2) Ask: ${leg_mid['ask']} | Bid: ${leg_mid['bid']}")
        print(f"Leg 3 ({upper_strike} C) Ask: ${leg_upper['ask']} | Bid: ${leg_upper['bid']}")
        print("--------------------------------------------------")
        print(f"butterfly Net Bid:   ${butterfly_bid:.2f}")
        print(f"butterfly Net Ask:   ${butterfly_ask:.2f}")
        print(f"butterfly Net Mid:   ${butterfly_mid:.2f} (Estimated Entry Cost)")
        print(f"butterfly max profit:   ${max_profit:.2f}")
        return response

    def get_spread_quote(self, underlying_symbol, contractType, nearer_strike, expiration_date=None, interval=5):
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
                interval = interval,
                daysToExpiration = 0,
                strategy="SINGLE"
            )
        else:
            response =  SchwabClient._client.option_chains(
                symbol=underlying_symbol,
                contractType=contractType,
                strikeCount=100,  # Broad strike buffer to ensure all 3 legs are included
                interval = interval,
                fromDate=expiration_date.strftime("%Y-%m-%d"),
                toDate=expiration_date.strftime("%Y-%m-%d"),
                strategy="SINGLE"
            )
        if response.status_code != 200:
            raise Exception(f"Failed to fetch option chain: {response.text}")

        data =self.get_quote(underlying_symbol)
        current_price = data[underlying_symbol]['quote']['lastPrice']

        chain_data = response.json()
        
        # Extract the map containing the call contracts
        call_map = chain_data.get('callExpDateMap', {})
        
        # Schwab formats expiration keys by joining the date and days-to-expiry (e.g., "2026-10-16:40")
        date_key = None
        for key in call_map.keys():
            if expiration_date is None or key.startswith(expiration_date.strftime("%Y-%m-%d")):
                date_key = key
                break
                
        if not date_key:
            raise ValueError(f"No option chain data found for expiration {expiration_date.strftime('%Y-%m-%d')}")
            
        expiry_chain = call_map[date_key]

        nearer_strike = nearer_strike
        farther_strike = nearer_strike + interval
        
        # 2. Isolate the specific legs
        try:
            # Schwab API uses string representation of floats for strike mapping (e.g., "150.0")
            leg_nearer = expiry_chain[f"{float(nearer_strike)}"][0] # Schwab wraps the strike contract payload in a list
            leg_farther = expiry_chain[f"{float(farther_strike)}"][0] # Schwab wraps the strike contract payload in a list
        except KeyError as e:
            raise KeyError(f"One of the specified strikes was not found in the chain: {e}")

        # 3. Aggregate the pricing for a Long Call Butterfly
        # Formula for Net Debit Entry: Cost of Outer Legs - Credit of Inner Legs
        # Maximize what you pay (ask) and minimize what you receive (bid) for the net ask spread limit.
        spread_bid = leg_nearer['bid'] - leg_farther['ask']
        spread_ask = leg_nearer['ask'] - leg_farther['bid']
        spread_mid = (spread_bid + spread_ask) / 2
        max_loss = abs(float(farther_strike) - float(nearer_strike)) * 100 - spread_mid  # Max loss occurs if the underlying is at or below nearer_strike at expiration
        max_profit = spread_mid  # Max profit occurs if the underlying is at or above farther_strike at expiration
        
        print(f"--- {underlying_symbol} Call Spread ({nearer_strike}/{farther_strike}) ---")
        if expiration_date:
            print(f"Expiration: {expiration_date.strftime('%Y-%m-%d')}")
        else:
            print("Expiration: Nearest available")
        print(f"Leg 1 ({nearer_strike} C) Ask: ${leg_nearer['ask']} | Bid: ${leg_nearer['bid']}")
        print(f"Leg 2 ({farther_strike} C) Ask: ${leg_farther['ask']} | Bid: ${leg_farther['bid']}")
        print("--------------------------------------------------")
        print(f"Spread Net Bid:   ${spread_bid:.2f}")
        print(f"Spread Net Ask:   ${spread_ask:.2f}")
        print(f"Spread Net Mid:   ${spread_mid:.2f} (Estimated Entry Cost)")
        print(f"Max Loss:   ${max_loss:.2f}")
        print(f"Max Profit:   ${max_profit:.2f}")
        return response

                
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

    #client.get_butterfly_quote('SPX', datetime.now(), 7655, 7645, 7665)
    client.get_butterfly_quote('$SPX', "CALL",7655, 7645, 7665,date(2026, 9, 16))
    client.get_spread_quote('$SPX', "CALL", 7675, expiration_date=None, interval=5)
