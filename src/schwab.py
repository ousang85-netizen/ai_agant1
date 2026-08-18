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
        if response.status_code >= 200 and response.status_code < 300:
            print(f"Order placed successfully: response.status_code = {response.status_code}")
            order_id = response.headers.get('location', '/').split('/')[-1]
            if order_id:
                self._orders.append(order_id)
        else:
            print(f"Failed to place order: response.status_code = {response.status_code}")
        return response

if __name__ == "__main__":
    client = SchwabClient()
    holdings = client.get_account_holdings()    
    print("\nStock Holdings:")
    for holding in holdings["stocks"]   :
        print(holding)

    print("\nOption Holdings:")
    for holding in holdings["options"]:
        print(holding)      

    client.place_order(symbol="IONX", quantity=100, action="BUY", price=31.48)
    client.order_details()  # Get details of the last order placed
    all=SchwabClient.account_orders().json()
    for order in all:
        print(order['orderLegCollection']['instrument']['symbol'])

