

from datetime import date, datetime, timedelta
import pandas as pd
#from thetadata import ThetaClient, Option, Right, DataType
from thetadata import ThetaClient


thetadata_api_key = "td1_prod_b931b3ba64254d829d8ed4d15e05018c"

def thetadata_print_option_history(symbol: str, expiration: date, strike: float, right: str):
    # Initialize the client (ensure Theta Terminal is running)

    client = ThetaClient(dataframe_type='pandas', api_key=thetadata_api_key)

    # Calculate the exact last 30 days
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=30)


    df_option = client.option_history_eod(
        start_date=start_dt,
        end_date=end_dt,
        symbol=symbol,
        expiration=expiration,
        strike=strike,
        right=right,
    )

    df_stock = client.stock_history_eod(
        start_date=start_dt,
        end_date=end_dt,
        symbol=symbol,
    )

    df_option['last_trade_short'] = df_option['last_trade'].dt.strftime('%Y-%m-%d')
    df_stock['last_trade_short'] = df_stock['last_trade'].dt.strftime('%Y-%m-%d')

    combined_df = pd.merge(df_option, df_stock, on='last_trade_short', suffixes=('_option', '_stock'))

    print(combined_df[['last_trade_short', 'close_option', 'bid_option', 'ask_option', 'close_stock']])

if __name__ == "__main__":
    thetadata_print_option_history('QQQ', date(2026, 11, 20), '650.0', 'call')
    
