# def check_partial_exit(trade: dict, ltp: float):
#     """
#     Executes partial exit at +0.8R
#     """
#     if trade["PARTIAL_DONE"]:
#         return trade, False

#     entry = trade["ENTRY"]
#     sl = trade["SL"]
#     side = trade["SIDE"]

#     r_value = abs(entry - sl)

#     if side == "BUY":
#         if ltp >= entry + (0.8 * r_value):
#             exit_qty = max(1, int(trade["QTY_REMAINING"] * 0.5))
#             trade, exit_qty = reduce_quantity(trade, exit_qty)
#             validate_quantity(trade)
#             trade["PARTIAL_DONE"] = True
#             return trade, exit_qty

#     return trade, False

def reduce_quantity(trade: dict, sell_qty: int):
    sell_qty = min(sell_qty, trade["QTY_REMAINING"])
    trade["QTY_REMAINING"] -= sell_qty
    return trade, sell_qty


def validate_quantity(trade: dict):
    if trade["QTY_REMAINING"] < 0:
        raise ValueError("QTY_REMAINING < 0")
    if trade["QTY_REMAINING"] > trade["QTY"]:
        raise ValueError("QTY_REMAINING > QTY")

def update_trailing_sl(trade: dict, ltp: float):
    """
    Trails SL after partial exit.
    SL only moves forward.
    """
    if not trade["PARTIAL_DONE"]:
        return trade, False

    atr = trade["ATR"]
    side = trade["SIDE"]

    if side == "BUY":
        new_sl = ltp - (1.5 * atr)

        if new_sl > trade["SL"]:
            trade["SL"] = new_sl
            trade["TRAILING_ACTIVE"] = True
            return trade, True

    return trade, False
