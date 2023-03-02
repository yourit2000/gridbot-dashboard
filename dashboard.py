from pandas.core.indexes.datetimes import datetime
import ccxt
import datetime as dt
import dateutil.parser
import time
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import streamlit as st
import streamlit_authenticator as stauth
import yaml


# put the hashed passwords into config.yaml
# hashed_passwords = stauth.Hasher(['apassword', 'anotherpassword']).generate()
# st.write(hashed_passwords)
#
with open('config.yaml') as file:
    config = yaml.load(file, Loader=yaml.SafeLoader)

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days'],
    config['preauthorized']
)

name, authentication_status, username = authenticator.login('Login', 'main')

if authentication_status:
    authenticator.logout('Logout', 'main')
    exchange = ccxt.bitstamp({
        'enableRateLimit': False,
        'apiKey': st.secrets["bitstamp_api_key"],
        'secret': st.secrets["bitstamp_secret"],
        })

    open_orders = exchange.fetch_open_orders()
    pairs = set([order['symbol'] for order in open_orders])
    prices = {pair: exchange.fetch_ticker(pair)['last'] for pair in pairs}

    selected_bot = st.sidebar.selectbox('Grid Bots', tuple(pairs))

    trades = exchange.fetch_my_trades()
    # put trades into a dataframe
    trades_df = pd.DataFrame(trades, columns=['id', 'datetime', 'symbol', 'side', 'price', 'amount', 'cost'])
    trades_df = trades_df.set_index('id')
    trades_df['datetime'] = pd.to_datetime(trades_df['datetime'])

    balances = exchange.fetch_balance()

    # ohlc = exchange.fetch_ohlcv(selected_bot, '5m')

    # fetch OHLCV bars
    def fetch_ohlcv(exchange, symbol, timeframe='15m'):
        if exchange.has['fetchOHLCV']:
            time.sleep (exchange.rateLimit / 1000) # time.sleep wants seconds
            olhc =  exchange.fetch_ohlcv(symbol, timeframe, limit=120) 
            df = pd.DataFrame(olhc, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df.timestamp = pd.to_datetime(df.timestamp, unit='ms')
            return df

    # check to see if bot is up? 
    st.title('🤖 Gridbot Dashboard') 

    olhc = fetch_ohlcv(exchange, selected_bot)
    fig = go.Figure(data=[go.Candlestick(x=olhc['timestamp'],
                                         open=olhc['open'],
                                         high=olhc['high'],
                                         low=olhc['low'],
                                         close=olhc['close'])])

    # draw horizontal lines at open orders
    for order in open_orders:
        if order['symbol'] == selected_bot:
            if order['side'] == 'buy':
                fig.add_hline(y=order['price'], line_width=1, line_dash="dash", line_color="blue")
            else:
                fig.add_hline(y=order['price'], line_width=1, line_dash="dash", line_color="red")

    fig.update_layout(
            title=selected_bot,
            xaxis_rangeslider_visible=False)
    st.plotly_chart(fig)

    st.header(f"{selected_bot} Bot")

    lookback_days = st.slider('Number of days:', min_value=1, max_value=30)
    today = dt.datetime.today()
    today = today.replace(tzinfo=dt.timezone.utc)

    # grab all trades the lookback_days ago
    lookback_df = trades_df[(trades_df['datetime'] > today - dt.timedelta(days=lookback_days)) & (trades_df['symbol'] == selected_bot)]
    st.write(lookback_df)

    sell_cost = lookback_df.loc[lookback_df['side'] == 'sell']['cost'].sum()
    buy_cost = lookback_df.loc[lookback_df['side'] == 'buy']['cost'].sum()

    col3, col4 = st.columns(2)
    col3.metric(f"All sell orders in last {lookback_days} days", f"${sell_cost:.2f}")
    col4.metric(f"All buy orders in the last {lookback_days} days", f"${buy_cost:.2f}")

    st.metric(f"{lookback_days} Days P&L", f"${sell_cost - buy_cost:.2f}")

    ##############
    # Pie Chart  #
    ##############
    st.header('Portfolio')
    cryptos = [crypto.split('/')[0] for crypto in pairs]
    values = [balances[crypto]['total'] * prices[crypto+'/USD'] for crypto in cryptos]

    cryptos.append('USD')
    values.append(balances['USD']['total'])

    fig = px.pie(balances, values=values, names=cryptos, title='🪙 Allocations')
    st.plotly_chart(fig)

    ###########
    # Sidebar #
    ###########
    st.sidebar.header('💰 Total Balance')

    # total_balance = balances['USD']
    total_balance = balances['USD']['total']
    # TODO: we can us the dataframe and vectorize this
    for crypto in cryptos:
        if crypto != 'USD':
            total_balance += balances[crypto]['total'] * prices[crypto+'/USD']
        
    st.sidebar.write(f"**${total_balance:.2f}** Total Balance")
    st.sidebar.write(f"**{total_balance/prices['BTC/USD']}** BTC")

    crypto = selected_bot.split('/')[0]
    st.sidebar.write(f'## {selected_bot} Balance')
    st.sidebar.write(f"**{balances[crypto]['used']}** {crypto} Used")
    st.sidebar.write(f"**{balances[crypto]['free']}** {crypto} Free")
    st.sidebar.write(f"**{balances[crypto]['total']}** {crypto} Total")

    st.sidebar.write('## USD Balance')
    st.sidebar.write(f"**${balances['USD']['used']}** Used")
    st.sidebar.write(f"**${balances['USD']['free']}** Free")
    st.sidebar.write(f"**${balances['USD']['total']}** Total")

    # TODO: Heartbeat to make sure bots are running

elif authentication_status is False:
    st.error('Username/password is incorrect')
elif authentication_status is None:
    st.warning('Please enter your username and password')
