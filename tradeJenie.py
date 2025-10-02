    # emalive.py

import time
import datetime
from datetime import timedelta
import pandas as pd
import sqlite3
import logging
from commonFunction import close_position_and_no_new_trade, convertIntoHeikinashi, delete_open_position, generate_godEma_signals, get_next_candle_time, get_optimal_option, get_trade_configs, hd_strategy, init_db, is_market_open, load_open_position, parallel_ema_strategy, record_trade, save_open_position, wait_until_next_candle, who_tried, will_market_open_within_minutes
from config import  SYMBOL,SEGMENT, CANDLE_DAYS as DAYS, REQUIRED_CANDLES, LOG_FILE,INSTRUMENTS_FILE, OPTION_SYMBOL, SERVER
from kitefunction import get_historical_df, place_option_hybrid_order, get_token_for_symbol, get_quotes
from telegrambot import send_telegram_message
import importlib
import threading
import pandas as pd
from requests.exceptions import ReadTimeout
from kiteconnect import exceptions
import random

# ====== Setup Logging ======
logging.basicConfig(
    filename=LOG_FILE,
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
instrument_token = get_token_for_symbol(SYMBOL)

if instrument_token is None:
    logging.error(f"❌ Instrument token for {SYMBOL} not found. Exiting.")
    exit(1)
logging.info(f"ℹ️ Instrument token for {SYMBOL}: {instrument_token} at current time {current_time}")

# ====== Main Live Trading Loconfig['TRADE']op ======
def live_trading(instruments_df, config, key, user):

    if config['TRADE'].lower() != "yes":
        print(f"🚫 {user['user']} {SERVER}  |  {key}  | TRADE mode is OFF SIMULATED_ORDER will be tracked")
        send_telegram_message(f"🛠️ {user['user']} {SERVER}  |  {key}  | OnlyLive {config['INTERVAL']} running in {'SIMULATION' if config['TRADE'].lower() != 'yes' else 'LIVE'} mode.",user['telegram_chat_id'], user['telegram_token'])
        logging.info(f"🚫 {user['user']} {SERVER}  |  {key}  | TRADE mode is OFF. Running in SIMULATION mode.")
    else:    
        print(f"🚀 {user['user']} {SERVER}  |  {key}  | TRADE mode is ON LIVE_ORDER will be placed")
        send_telegram_message(f"🚀 {user['user']} {SERVER}  |  {key}  | {config['INTERVAL']} Live trading started!",user['telegram_chat_id'], user['telegram_token'])
        logging.info(f"🚀 {user['user']} {SERVER}  |  {key}  | TRADE mode is ON. Running in LIVE mode.")

    open_trade = load_open_position(config, key, user, user['id'])

    if open_trade:
        trade = open_trade
        position = open_trade["Signal"]
        logging.info(f"📌 {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Resumed open position: {position} | {open_trade['OptionSymbol']} @ ₹{open_trade['OptionSellPrice']} | Qty: {open_trade['qty']}")
        print(f"➡️ {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Loaded open position: {open_trade}")
        send_telegram_message(f"📌 {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Resumed open position: {position} | {open_trade['OptionSymbol']} @ ₹{open_trade['OptionSellPrice']} | Qty: {open_trade['qty']}",user['telegram_chat_id'], user['telegram_token'])
    else:
        trade = {}
        position = None
        print(f"ℹ️ {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} No open position. Waiting for next signal...")
        logging.info(f"ℹ️ {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} No open position. Waiting for next signal...")

    # if not is_market_open():
    #     print(f"🕒 {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Market is currently closed. Live trading will start once the market opens.")
    #     send_telegram_message(f"🕒 {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Market is currently closed. Live trading will start once the market opens.")
    #     return

    while True:
        try:
            configs = get_trade_configs(user['id'])
            config = configs[key]
            if config['NEW_TRADE'].lower() == "no" and trade == {}:   
                print(f"🚫 {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']}, There is no live trade present, No new trades allowed. So Closing the program")
                logging.info(f"🚫{user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']}, There is no live trade present, No new trades allowed. So Closing the program")
                send_telegram_message(f"🕒 {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']}, There is no live trade present, No new trades allowed. So Closing the program",user['telegram_chat_id'], user['telegram_token'])
                break    
            
            

            if not is_market_open():
                print(f"{user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Market is closed. Checking if market will open within 60 minutes...")
                if will_market_open_within_minutes(60):
                    print(f"{user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Market will open within 60 minutes. Continuing to wait...")
                    time.sleep(60)
                    continue
                else:
                    print(f"{user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Market will not open within 60 minutes. Stopping program.")
                    send_telegram_message(f"🛑 {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Market will not open within 60 minutes. Stopping program.",user['telegram_chat_id'], user['telegram_token'])
                    return

            if config['INTRADAY'].lower() == "yes" and trade == {} and datetime.datetime.now().time() >= datetime.time(15, 15):
                print(f"🚫 {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']}, There is no live trade present, No new trades allowed. So Closing the program")
                logging.info(f"🚫{user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']}, There is no live trade present, No new trades allowed. So Closing the program")
                send_telegram_message(f"🕒 {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']}, There is no live trade present, No new trades allowed. So Closing the program",user['telegram_chat_id'], user['telegram_token'])
                break     

            df = get_historical_df(instrument_token, config['INTERVAL'], DAYS, user)
            print(f"🕵️‍♀️ {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Candles available: {len(df)} / Required: {REQUIRED_CANDLES}")

            if len(df) < REQUIRED_CANDLES:
                print(f"⚠️ {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Not enough candles. Waiting...")
                time.sleep(60)
                continue
            
            if config['STRATEGY'] == "GOD_EMA":
                df = generate_godEma_signals(df)
            elif config['STRATEGY'] == "HDSTRATEGY":
                df = convertIntoHeikinashi(df)
                df = hd_strategy(df)
            elif config['STRATEGY'] == "PARALLEL_EMA":
                df = parallel_ema_strategy(df)
            
            latest = df.iloc[-1]
            latest_time = pd.to_datetime(latest['date'])
            # now = datetime.now()

            # ✅ Decide which row to use for signals
            if df.iloc[-1]['buySignal'] or df.iloc[-1]['sellSignal']:
                latest = df.iloc[-1]
            elif df.iloc[-2]['buySignal'] or df.iloc[-2]['sellSignal']:
                latest = df.iloc[-2]
            else:
                latest = df.iloc[-1]  # No signal in last 2 candles

            ts = latest['date'].strftime('%Y-%m-%d %H:%M')
            close = latest['close']
            current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            logging.info(f"{config['STRATEGY']} | INTERVAL {config['INTERVAL']} | Candle time {ts} | Close: {close} | Buy: {latest['buySignal']} | Sell: {latest['sellSignal']} | Trend: {latest['trend']} | Current Time: {current_time}")
            print(f"{config['STRATEGY']} | Candle time {ts} | Close: {close} | Buy: {latest['buySignal']} | Sell: {latest['sellSignal']} | Trend: {latest['trend']} | Current Time: {current_time}")

            # ✅ BUY SIGNAL
            if latest['buySignal'] and position != "BUY":
                if position == "SELL":
                    trade.update({
                        "SpotExit": close,
                        "ExitTime": ts,
                        "OptionBuyPrice": get_quotes(trade["OptionSymbol"] , user),
                    })
                    trade["PnL"] = trade["OptionSellPrice"] - trade["OptionBuyPrice"]
                    trade["qty"] = trade.get("qty",config['QTY'])
                    print(f"📥 {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Exiting SELL: Buying back {trade['OptionSymbol']} | Qty: {trade['qty']}")
                    logging.info(f"📥INTERVAL {config['INTERVAL']} | Exiting SELL: Buying back {trade['OptionSymbol']} | Qty: {trade['qty']}")
                    
                    order_id ,avg_price,qty = place_option_hybrid_order(trade["OptionSymbol"], trade["qty"], "BUY",config, user)
                    logging.info(f"order_id : {order_id} | opt_symbol : {trade['OptionSymbol']} avg_price : {avg_price} | qty : {qty}")
                    if avg_price is None:
                        avg_price = get_quotes(trade["OptionSymbol"], user)
                        qty = config['QTY']
                    trade.update({
                        "OptionBuyPrice": avg_price,
                        "ExitTime": ts,
                        "PnL": trade["OptionSellPrice"] - avg_price,
                        "qty": qty,
                        "ExitReason": "SIGNAL_GENERATED"
                    })  
                    logging.info(f"📥INTERVAL {config['INTERVAL']} | Exiting SELL: Buying back {trade['OptionSymbol']} | Qty: {trade['qty']}")
                    record_trade(trade, config, user['id'])
                    delete_open_position(trade["OptionSymbol"], config, trade, user['id'])
                    send_telegram_message(f"📤INTERVAL {config['INTERVAL']} | {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Exit SELL\n{trade['OptionSymbol']} @ ₹{trade['OptionBuyPrice']:.2f}",user['telegram_chat_id'], user['telegram_token'])

                if config['NEW_TRADE'].lower() == "no":
                    print(f"🚫 {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} No new trades allowed. Skipping BUY signal.")
                    logging.info(f"🚫INTERVAL {config['INTERVAL']} | {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} No new trades allowed. Skipping BUY signal.")
                    break

                result = get_optimal_option("BUY", close, config['NEAREST_LTP'], instruments_df, config, user)
                
                if result is None or result[0] is None:
                    logging.error(f"❌INTERVAL {config['INTERVAL']} | {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']}: No suitable option found for BUY signal.")
                    send_telegram_message(f"❌INTERVAL {config['INTERVAL']} | {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']}: No suitable option found for BUY signal.",user['telegram_chat_id'], user['telegram_token'])
                    continue
                else:
                    opt_symbol, strike, expiry, ltp = result
                    print(f"📤INTERVAL {config['INTERVAL']} | {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Entering BUY: {opt_symbol} | Strike: {strike} | Expiry: {expiry} | LTP: ₹{ltp:.2f}")
                    logging.info(f"📤INTERVAL {config['INTERVAL']} | {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Entering BUY: {opt_symbol} | Strike: {strike} | Expiry: {expiry} | LTP: ₹{ltp:.2f}")
                    
                    order_id ,avg_price,qty = place_option_hybrid_order(opt_symbol, config['QTY'], "SELL", config, user)
                    logging.info(f"order_id : {order_id} | opt_symbol : {opt_symbol} avg_price : {avg_price} | qty : {qty}")
                    logging.info(f"📤INTERVAL {config['INTERVAL']} | Entering BUY: Selling PE {opt_symbol} | Qty: {config['QTY']}")
                    time.sleep(2)
                    
                    
                   
                    if avg_price is None:
                        avg_price = ltp
                        qty = config['QTY']

                    logging.info(f"📤INTERVAL {config['INTERVAL']} | Avg price for {opt_symbol}: ₹{avg_price:.2f} | Qty: {qty}")

                    trade = {
                        "Signal": "BUY", "SpotEntry": close, "OptionSymbol": opt_symbol,
                        "Strike": strike, "Expiry": expiry,
                        "OptionSellPrice": avg_price, "EntryTime": ts,
                        "qty": qty, "interval": config['INTERVAL'], "real_trade": config['TRADE'],
                        "EntryReason":"SIGNAL_GENERATED", "ExpiryType":config['EXPIRY'],
                        "Strategy":config['STRATEGY'], "Key":key
                    }
                    save_open_position(trade, config, user['id'])
                    position = "BUY"
                    send_telegram_message(f"🟢INTERVAL {config['INTERVAL']} | {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Buy Signal\n{opt_symbol} | Avg ₹{avg_price:.2f} | Qty: {qty}",user['telegram_chat_id'], user['telegram_token'])

            # ✅ SELL SIGNAL
            elif latest['sellSignal'] and position != "SELL":
                if position == "BUY":
                    trade.update({
                        "SpotExit": close,
                        "ExitTime": ts,
                        "OptionBuyPrice": get_quotes(trade["OptionSymbol"], user),
                    })
                    trade["PnL"] = trade["OptionSellPrice"] - trade["OptionBuyPrice"]
                    trade["qty"] = trade.get("qty", config['QTY'])
                    print(f"📥 {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Exiting BUY: Buying back {trade['OptionSymbol']} | Qty: {trade['qty']}")
                    logging.info(f"📥INTERVAL {config['INTERVAL']} | Exiting BUY: Buying back {trade['OptionSymbol']} | Qty: {trade['qty']}")
                    
                    order_id ,avg_price,qty = place_option_hybrid_order(trade["OptionSymbol"], trade["qty"], "BUY", config, user)
                    logging.info(f"order_id : {order_id} | opt_symbol : {trade['OptionSymbol']} avg_price : {avg_price} | qty : {qty}")
                    logging.info(f"📥INTERVAL {config['INTERVAL']} | Exiting BUY: Buying back {trade['OptionSymbol']} | Qty: {trade['qty']}")
                    if avg_price is None:
                        avg_price = get_quotes(trade["OptionSymbol"], user) or 0.0
                        qty = config['QTY']
                    trade.update({
                        "OptionBuyPrice": avg_price,
                        "ExitTime": ts,
                        "PnL": trade["OptionSellPrice"] - avg_price,
                        "qty": qty,
                        "ExitReason": "SIGNAL_GENERATED"
                    })
                    record_trade(trade, config, user['id'])
                    delete_open_position(trade["OptionSymbol"], config, trade, user['id'])
                    send_telegram_message(f"📤 {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Exit BUY\n{trade['OptionSymbol']} @ ₹{trade['OptionBuyPrice']:.2f}",user['telegram_chat_id'], user['telegram_token'])

                if config['NEW_TRADE'].lower() == "no":
                    print(f"🚫INTERVAL {config['INTERVAL']} | {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} No new trades allowed. Skipping SELL signal.")
                    logging.info(f"🚫INTERVAL {config['INTERVAL']} | {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} No new trades allowed. Skipping SELL signal.")
                    break

                result = get_optimal_option("SELL", close, config['NEAREST_LTP'], instruments_df, config, user)
                if result is None or result[0] is None:
                    logging.error(f"❌INTERVAL {config['INTERVAL']} | {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']}: No suitable option found for SELL signal.")
                    send_telegram_message(f"❌ {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']}: No suitable option found for SELL signal.",user['telegram_chat_id'], user['telegram_token'])
                    continue
                else:
                    opt_symbol, strike, expiry, ltp = result
                    print(f"📤 {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Entering SELL: {opt_symbol} | Strike: {strike} | Expiry: {expiry} | LTP: ₹{ltp:.2f}")
                    logging.info(f"📤 {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Entering SELL: {opt_symbol} | Strike: {strike} | Expiry: {expiry} | LTP: ₹{ltp:.2f}")
                    
                    order_id ,avg_price,qty = place_option_hybrid_order(opt_symbol, config['QTY'], "SELL", config, user)
                    logging.info(f"order_id : {order_id} | opt_symbol : {opt_symbol} avg_price : {avg_price} | qty : {qty}")
                    (opt_symbol, config['QTY'], "SELL")
                    logging.info(f"📤 Entering SELL: Selling CE {opt_symbol} | Qty: {config['QTY']}")
                    time.sleep(2)
                   
                    if avg_price is None:
                        avg_price = ltp
                        qty = config['QTY']

                    trade = {
                        "Signal": "SELL", "SpotEntry": close, "OptionSymbol": opt_symbol,
                        "Strike": strike, "Expiry": expiry,
                        "OptionSellPrice": avg_price, "EntryTime": ts,
                        "qty": qty,  "interval": config['INTERVAL'], "real_trade": config['TRADE'],
                        "EntryReason":"SIGNAL_GENERATED", "ExpiryType":config['EXPIRY'],
                        "Strategy":config['STRATEGY'], "Key":key
                    }
                    save_open_position(trade, config, user['id'])
                    position = "SELL"
                    send_telegram_message(f"🔴 {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Sell Signal\n{opt_symbol} | Avg ₹{avg_price:.2f} | Qty: {qty}",user['telegram_chat_id'], user['telegram_token'])


            next_candle_time = get_next_candle_time(config['INTERVAL'])
            # ✅ Add this flag before the while loop
            target_hit = False
            while datetime.datetime.now() < next_candle_time:
                # Actively monitor current position LTP
                if trade and "OptionSymbol" in trade:
                    current_ltp = get_quotes(trade["OptionSymbol"] ,user)
                    entry_ltp = trade["OptionSellPrice"]
                    if current_ltp != None and entry_ltp != None:
                        yestime = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        percent_change = round(((current_ltp - entry_ltp) / entry_ltp) * 100,2)
                        print(f"{user['user']} | {config['STRATEGY']}  |  {config['INTERVAL']} position at {yestime}: {trade['Signal']} | {trade['OptionSymbol']} | Entry LTP: ₹{entry_ltp:.2f} | Current LTP: ₹{current_ltp:.2f} | Chg % {percent_change} | Qty: {trade['qty']}")
                # logging.info(f"PMK  {INTERVAL} Monitoring position at {yestime}: {trade['Signal']} | {trade['OptionSymbol']} | Entry LTP: ₹{entry_ltp:.2f} | Current LTP: ₹{current_ltp:.2f} | Qty: {trade['qty']}")
                # ✅ Intraday  EXIT 
                now = datetime.datetime.now()
                if now.time().hour == 15 and now.time().minute >= 15 and trade and "OptionSymbol" in trade and position:
                    if config['INTRADAY'] == "yes":
                        trade, position = close_position_and_no_new_trade(trade, position, close, ts,config, user)
                        print(f"⏰ {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Intraday mode: No new trades after 3:15 PM. Waiting for market close.")
                        logging.info(f"⏰ {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Intraday mode: No new trades after 3:15 PM. Waiting for market close.")
                        send_telegram_message(f"⏰ {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Intraday mode: No new trades after 3:15 PM. Waiting for market close.",user['telegram_chat_id'], user['telegram_token'])
                        break

                # ✅ Target Achieved and Re-Entry
                if trade and "OptionSymbol" in trade and "OptionSellPrice" in trade and config['ROLLOVER'] == 'yes' and target_hit == False:
                    current_ltp = get_quotes(trade["OptionSymbol"] ,user)
                    entry_ltp = trade["OptionSellPrice"]

                    if current_ltp != None and entry_ltp != None and entry_ltp != 0.0 and current_ltp <= 0.6 * entry_ltp:
                        target_hit = True  # Set the flag to True to avoid multiple triggers
                        trade["SpotExit"] = close
                        trade["ExitTime"] = ts
                        trade["OptionBuyPrice"] = current_ltp
                        trade["PnL"] = entry_ltp - current_ltp
                        print(f"📥 {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Target Exit: Buying back {trade['OptionSymbol']} | Qty: {trade['qty']}")
                        logging.info(f"📥INTERVAL {config['INTERVAL']} | Target Exit: Buying back {trade['OptionSymbol']} | Qty: {trade['qty']}")
                        
                        order_id ,avg_price,qty = place_option_hybrid_order(trade["OptionSymbol"], trade["qty"], "BUY", config, user)
                        logging.info(f"order_id : {order_id} | opt_symbol : {trade['OptionSymbol']} avg_price : {avg_price} | qty : {qty}")
                        logging.info(f"📥 Target Exit: Buying back {trade['OptionSymbol']} | Qty: {trade['qty']}")
                        if avg_price is None:
                            avg_price = current_ltp
                            qty = config['QTY']
                        trade.update({
                            "OptionBuyPrice": avg_price,
                            "ExitTime": ts,
                            "PnL": entry_ltp - avg_price,
                            "qty": qty,
                            "ExitReason": "TARGET_HIT"
                        })
                        record_trade(trade, config, user['id'])
                        delete_open_position(trade["OptionSymbol"], config, trade, user['id'])
                        send_telegram_message(f"📤 {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Exit {trade['Signal']}\n{trade['OptionSymbol']} @ ₹{current_ltp:.2f}",user['telegram_chat_id'], user['telegram_token'])
                        logging.info(f"🔴 {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Target triggered for {trade['OptionSymbol']} at ₹{current_ltp:.2f}")

                        last_expiry = trade["Expiry"]
                        signal = trade["Signal"]
                        trade = {}
                        
                        if config['NEW_TRADE'].lower() == "no":
                            print(f"🚫 {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} No new trades allowed after target exit.")
                            logging.info(f"🚫 {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} No new trades allowed after target exit.")
                            position = None
                            break
                        
                        
                        result = get_optimal_option(signal, close, config['NEAREST_LTP'], instruments_df, config, user)
                        
                        if result is None or result[0] is None:
                            logging.error(f"❌INTERVAL {config['INTERVAL']} | No expiry found after {last_expiry} for reentry.")
                            position = None
                            continue
                        else:
                            opt_symbol, strike, expiry, ltp = result
                            print(f"🔁 Reentry: {signal} at {opt_symbol} | Strike: {strike} | Expiry: {expiry} | LTP: ₹{ltp:.2f}")
                            logging.info(f"🔁INTERVAL {config['INTERVAL']} | Reentry: {signal} at {opt_symbol} | Strike: {strike} | Expiry: {expiry} | LTP: ₹{ltp:.2f}")
                            
                            order_id ,avg_price,qty = place_option_hybrid_order(opt_symbol, config['QTY'], "SELL", config, user)
                            logging.info(f"order_id : {order_id} | opt_symbol : {opt_symbol} avg_price : {avg_price} | qty : {qty}")
                            logging.info(f"🔁INTERVAL {config['INTERVAL']} | Reentry: Selling {opt_symbol} | Qty: {config['QTY']}")
                            time.sleep(2)

                            if avg_price is None:
                                avg_price = ltp
                                qty = config['QTY']

                            trade = {
                                "Signal": signal,
                                "SpotEntry": close,
                                "OptionSymbol": opt_symbol,
                                "Strike": strike,
                                "Expiry": expiry,
                                "OptionSellPrice": avg_price,
                                "EntryTime": ts,
                                "qty": qty, 
                                "interval": config['INTERVAL'],
                                "real_trade": config['TRADE'],
                                "EntryReason":"ROLLOVER",
                                "ExpiryType":config['EXPIRY'],
                                "Strategy":config['STRATEGY'],
                                "Key":key
                            }
                            save_open_position(trade, config, user['id'])
                            send_telegram_message(f"🔁 {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Reentry {signal}\n{opt_symbol} | Avg ₹{avg_price:.2f} | Qty: {qty}",user['telegram_chat_id'], user['telegram_token'])
                            position = signal
                

                random_number = random.randint(7, 15)
                time.sleep(random_number)

                
        except ReadTimeout as re:
            # Ignore read timeout
            logging.error(f"⚠️ {user['user']} {SERVER}  |  {key}  | Exception: {re}", exc_info=True)
            pass


        except exceptions.NetworkException:
            # Ignore network exception
            pass

        
        except Exception as e:
            logging.error(f"{user['user']} {SERVER}  | Exception: {e}", exc_info=True)
            send_telegram_message(f"⚠️ {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Error: {e}",user['telegram_chat_id'], user['telegram_token'])
            time.sleep(60)



# ====== Run ======
def init_and_run(user):
    while True:
        try:
            who_tried(user)
            
            instruments_df = pd.read_csv(INSTRUMENTS_FILE)
            threads = []
            configs = get_trade_configs(user['id'])
            keys = configs.keys()
            for key in keys:
                config = configs[key]
                init_db()
                t = threading.Thread(target=live_trading, args=(instruments_df, config, key, user))
                t.start()
                threads.append(t)
            for t in threads:
                t.join()
            break
        except Exception as e:
            logging.error(f"Fatal error: {e}")
            logging.error("Restarting emalive in 10 seconds...")
            time.sleep(10)
