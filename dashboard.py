import ccxt
import datetime as dt
import time
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import streamlit as st
import streamlit_authenticator as stauth
import streamlit_autorefresh
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

    count = streamlit_autorefresh.st_autorefresh(interval=5 * 60 * 1000, key="chartcounter")

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

    ohlc = fetch_ohlcv(exchange, selected_bot)
    fig = go.Figure(data=[go.Candlestick(x=ohlc['timestamp'],
                                         open=ohlc['open'],
                                         high=ohlc['high'],
                                         low=ohlc['low'],
                                         close=ohlc['close'])])

    # draw horizontal lines at open orders
    for order in open_orders:
        if order['symbol'] == selected_bot:
            if order['side'] == 'buy':
                fig.add_hline(y=order['price'], line_width=1, line_dash="dash", line_color="blue")
            else:
                fig.add_hline(y=order['price'], line_width=1, line_dash="dash", line_color="red")

    fig.update_layout(
            title=selected_bot,
            xaxis_range=[ohlc['timestamp'].iloc[0], ohlc['timestamp'].iloc[-1] + dt.timedelta(hours=4)],
            xaxis_rangeslider_visible=False)

    st.plotly_chart(fig)

    st.header(f"{selected_bot} Bot")

    lookback_days = st.slider('Number of days:', min_value=1, max_value=30)
    today = dt.datetime.today()
    today = today.replace(tzinfo=dt.timezone.utc)

    # grab all trades the lookback_days ago
    lookback_df = trades_df[(trades_df['datetime'] > today - dt.timedelta(days=lookback_days)) & (trades_df['symbol'] == selected_bot)]
    st.write(lookback_df)

    sell_amount = lookback_df.loc[lookback_df['side'] == 'sell']['amount'].sum()
    buy_amount = lookback_df.loc[lookback_df['side'] == 'buy']['amount'].sum()
    

    col3, col4 = st.columns(2)
    col3.metric(f"All buy orders in the last **{lookback_days}** days", f"{buy_amount:.2f} {selected_bot}")
    col4.metric(f"All sell orders in last **{lookback_days}** days", f"{sell_amount:.2f} {selected_bot}")

    # st.metric(f"{lookback_days} Days P&L", f"${sell_cost - buy_cost:.2f}")
    sell_cost_basis = lookback_df.loc[lookback_df['side'] == 'sell']['cost'].sum() * -1
    buy_cost_basis = lookback_df.loc[lookback_df['side'] == 'buy']['cost'].sum()

    cost_basis = buy_cost_basis + sell_cost_basis

    current_price = prices[selected_bot]

    diff = sell_amount - buy_amount
    diff_cost = diff * current_price

    # since we make money on the sell side it is relected as negative when profitable
    # so change the sign
    profit = cost_basis + diff_cost  
    profit = profit * -1

    st.metric(f"**{lookback_days}** Days P&L", f"${profit:.2f}")

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

    ##############
    # Sidebar    #
    ##############
    crypto = selected_bot.split('/')[0]
    st.sidebar.write(f'## {selected_bot} Balance')
    st.sidebar.write(f"**{balances[crypto]['used']:.4f}** {crypto} Used")
    st.sidebar.write(f"**{balances[crypto]['free']:.4f}** {crypto} Free")
    st.sidebar.write(f"**{balances[crypto]['total']:.4f}** {crypto} Total")

    st.sidebar.write('## USD Balance')
    st.sidebar.write(f"**${balances['USD']['used']}** Used")
    st.sidebar.write(f"**${balances['USD']['free']}** Free")
    st.sidebar.write(f"**${balances['USD']['total']}** Total")

    st.sidebar.header('💰 Total Balance')

    
    total_balance = balances['USD']['total']
    for crypto in cryptos:
        if crypto != 'USD':
            total_balance += balances[crypto]['total'] * prices[crypto+'/USD']

    btc_usd = exchange.fetch_ticker('BTC/USD')['last']
    st.sidebar.write(f"**${total_balance:.2f}**  🚀 **{total_balance/btc_usd:.4f}** BTC")
    
    # deposits 
    # not implemented in ccxt yet
    # deposits = exchange.fetch_deposits()
    # st.sidebar.write(deposits)

elif authentication_status is False:
    st.error('Username/password is incorrect')
elif authentication_status is None:
    st.warning('Please enter your username and password')
