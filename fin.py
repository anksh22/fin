import time
import logging
import json
import requests

logging.basicConfig(level=logging.DEBUG)

# User defined parameters
USERNAME = "your_username"
PASSWORD = "your_password"
INSTRUMENT_TOKEN = "1376258" # FinNifty
OPTION_TYPE = "CE" # CE or PE
OPTION_PRICE_RANGE = "LT15" # LT15 (less than or equal to 15), GT15 (greater than 15), NEAR100 (nearest to 100)
TIME_TO_PLACE_ORDER = "09:35:00"
SL_PERCENTAGE = 21
LIMIT_SELL_PERCENTAGE = 2

def login(username, password):
    kite_login_url = "https://api.kite.trade/session/token"
    resp = requests.post(kite_login_url, data={"user_id": username, "password": password})
    if resp.status_code != 200:
        raise Exception("Failed to login")

    logging.debug(resp.content)
    response_data = json.loads(resp.content.decode("utf-8"))
    access_token = response_data["data"]["access_token"]
    return access_token

def get_option_chain(token, instrument_token, option_type, option_price_range):
    option_chain_url = f"https://api.kite.trade/instruments/{instrument_token}/options"
    resp = requests.get(option_chain_url, headers={"Authorization": f"Bearer {token}"})

    if resp.status_code != 200:
        raise Exception("Failed to get option chain")

    option_chain = json.loads(resp.content.decode("utf-8"))
    if option_price_range == "LT15":
        option_chain_filtered = [option for option in option_chain[option_type] if option["last_price"] and option["last_price"] <= 15]
    elif option_price_range == "GT15":
        option_chain_filtered = [option for option in option_chain[option_type] if option["last_price"] and option["last_price"] > 15]
    else: # NEAR100
        option_chain_filtered = sorted(option_chain[option_type], key=lambda x: abs(x["last_price"] - 100))
    return option_chain_filtered

def place_order(token, instrument_token, order_type, quantity, price, trigger_price):
    order_place_url = "https://api.kite.trade/orders/regular"
    data = {
        "tradingsymbol": f"FINNIFTY20JUN{OPTION_TYPE}{instrument_token[-2:]}",
        "quantity": quantity,
        "exchange": "NFO",
        "order_type": order_type,
        "product": "NRML",
        "validity": "DAY",
        "price": price,
        "trigger_price": trigger_price,
        "transaction_type": "SELL" if order_type == "SL" else "BUY",
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.post(order_place_url, headers=headers, data=json.dumps(data))

    if resp.status_code != 200:
        raise Exception(f"Failed to place {order_type} order")

    order_data = json.loads(resp.content.decode("utf-8"))["data"]
    order_id = order_data["order_id"]
    return order_id

def modify_order(token, order_id, price):
    modify_order_url = f"https://api.kite.trade/orders/{order_id}"
    data = {
        "order_id": order_id,
        "price": price,
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.put(modify_order_url, headers=headers, data=json.dumps(data))

        if resp.status_code != 200:
        raise Exception("Failed to get user profile")
    
    user_profile = json.loads(resp.content.decode("utf-8"))["data"]["user_type"]
    return user_profile

if __name__ == "__main__":
    logging.info("Logging in...")
    token = login(USERNAME, PASSWORD)

    logging.info("Getting user profile...")
    #user_profile = get_user_profile(token)
    #logging.info(f"User profile: {user_profile}")

    logging.info("Getting option chain...")
    option_chain = get_option_chain(token, INSTRUMENT_TOKEN, OPTION_TYPE, OPTION_PRICE_RANGE)
    logging.debug(option_chain)

    # Select option to trade
    option = option_chain[0]
    option_strike_price = option["strike"]
    option_ltp = option["last_price"]
    option_quantity = 75

    # Calculate buy, sell and stop loss prices
    buy_price = round(option_ltp * 1.01, 2)
    sell_price = round(option_ltp * 1.015, 2)
    sl_price = round(option_ltp * (1 - SL_PERCENTAGE / 100), 2)
    sl_trigger_price = round(option_ltp * (1 - (SL_PERCENTAGE + 1) / 100), 2)

    logging.info(f"Selected option: {option}")
    logging.info(f"Option buy price: {buy_price}")
    logging.info(f"Option sell price: {sell_price}")
    logging.info(f"Option SL price: {sl_price}")
    logging.info(f"Option SL trigger price: {sl_trigger_price}")

    # Place limit buy order
    limit_buy_order_id = place_order(token, INSTRUMENT_TOKEN, "LIMIT", option_quantity, buy_price, 0)
    logging.info(f"Limit buy order placed with ID: {limit_buy_order_id}")

    # Monitor the order until it gets executed
    while True:
        order_details = get_order_details(token, limit_buy_order_id)
        if order_details["status"] == "COMPLETE":
            logging.info(f"{order_details['order_type']} order executed. Details: {order_details}")
            break
        else:
            logging.debug(f"Order status: {order_details['status']}. Waiting...")
            time.sleep(1)

    # Place SL order to sell option with stop loss
    sl_order_id = place_order(token, INSTRUMENT_TOKEN, "SL", option_quantity, sl_price, sl_trigger_price)
    logging.info(f"SL order placed with ID: {sl_order_id}")

    # Monitor SL order status and place limit sell order if executed
    while True:
        order_details = get_order_details(token, sl_order_id)
        if order_details["status"] == "COMPLETE":
            logging.info("SL order executed")
            limit_sell_price = round(sell_price * (1 + LIMIT_SELL_PERCENTAGE / 100), 2)
            limit_sell_order_id = place_order(token, INSTRUMENT_TOKEN, "LIMIT", option_quantity, limit_sell_price, 0)
            logging.info(f"Limit sell order placed with ID: {limit_sell_order_id}")
            break
        time.sleep(2)