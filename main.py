#!/usr/bin/env python3
"""auto arbitrage."""
import os
import os.path
import dotenv
import ccxt.async as ccxt
import time
import asyncio
import numpy as np
from traceback import print_exc


def main() -> int:
    """main."""
    inited = init()
    capacity = fetchCapacity(inited)
    while True:
        try:
            # bitbank ETH JP
            # hitbtc ETH BTC(bitbankのBTC/JPで換算)
            value = fetchValue(inited)
            capacity = attemptTrade(inited, capacity, value)
            time.sleep(3)
        except Exception:
            print_exc()
            time.sleep(5)
            capacity = fetchCapacity(inited)
    return 0


def init():
    """apiなど初期化."""
    dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
    dotenv.load_dotenv(dotenv_path)
    hitbtc2 = ccxt.hitbtc2({
        'apiKey': os.environ.get('hitbtc2_key'),
        'secret': os.environ.get('hitbtc2_secret')})
    bitbank = ccxt.bitbank({
        'apiKey': os.environ.get('bitbank_key'),
        'secret': os.environ.get('bitbank_secret')})
    el = asyncio.get_event_loop()
    (hitbtc2Markets, bitbankMarkets) = el.run_until_complete(asyncio.gather(
        hitbtc2.load_markets(),
        bitbank.load_markets()))
    minUnit = {
        'bitbank': {
            'XRP/JPY': 0.0001,
            'BTC/JPY': 0.0001},
        'hitbtc2': {
            'XRP/BTC': hitbtc2Markets['XRP/BTC']['limits']['amount']['min']}}
    return {'hitbtc2': hitbtc2, 'bitbank': bitbank, 'minUnit': minUnit}


def attemptTrade(inited, capacity, value):
    """判断 トレード 余力取得."""
    production = False
    hitbtc2 = {
        'asks': np.array(value['hitbtc2']['XRP/BTC']['asks'][:10]),
        'bids': np.array(value['hitbtc2']['XRP/BTC']['bids'][:10])}
    bitbankXrp = {
        'asks': np.array(value['bitbank']['XRP/JPY']['asks'][:10]),
        'bids': np.array(value['bitbank']['XRP/JPY']['bids'][:10])}
    bitbankJpy = {  # JPY/BTC (JPY1円あたりのBTC枚数, 円)
        'asks': np.array([
            [1 / x[0], x[1] * x[0]]
            for x in value['bitbank']['BTC/JPY']['bids'][:10]]),
        'bids': np.array([
            [1 / x[0], x[1] * x[0]]
            for x in value['bitbank']['BTC/JPY']['asks'][:10]])}

    # XRPの枚数で取引量を示す
    # 1: BASE2/BASE1, 2: ALT/BASE2, 3: ALT/BASE1
    # 1: JPY/BTC, 2: XRP/JPY, 3: XRP/BTC
    (ratioS, valS) = calcSellingTwice(
        bitbankJpy['bids'],
        bitbankXrp['bids'],
        hitbtc2['asks'], 1.002)
    (ratioB, valB) = calcBuyingTwice(
        bitbankJpy['asks'],
        bitbankXrp['asks'],
        hitbtc2['bids'], 1.002)
    print((ratioS, valS, ratioB, valB))
    minUnit = max([
        inited['minUnit']['bitbank']['BTC/JPY'] /
        bitbankJpy['bids'][-1][0] /
        bitbankXrp['bids'][-1][0],
        inited['minUnit']['hitbtc2']['XRP/BTC'],
        inited['minUnit']['bitbank']['XRP/JPY']])
    doTrade = (
        1 if ratioS >= 1.002 else
        -1 if ratioB >= 1.002 else
        0)
    if not doTrade:
        return capacity
    elif doTrade == 1:  # 2回売る
        # print([
        #     capacity['bitbank']['XRP'],
        #     capacity['bitbank']['JPY'] * bitbankXrp['bids'][-1][0],
        #     capacity['hitbtc2']['BTC'] / hitbtc2['asks'][-1][0]])
        cap = min([
            capacity['bitbank']['XRP'],
            capacity['bitbank']['JPY'] * bitbankXrp['bids'][-1][0],
            capacity['hitbtc2']['BTC'] / hitbtc2['asks'][-1][0]])
        val = min([cap * 0.8, valS])
    elif doTrade == -1:  # 2回買う
        cap = min([
            capacity['bitbank']['JPY'] / bitbankXrp['asks'][-1][0],
            capacity['bitbank']['BTC'] /
            bitbankJpy['asks'][-1][0] /
            bitbankXrp['asks'][-1][0],
            capacity['hitbtc2']['XRP']])
        val = min([cap * 0.8, valB])
    # print((val, valS, valB))
    priceXrpJpy = (
        bitbankXrp['asks'][0][0] * 1.01 if doTrade == -1 else
        bitbankXrp['bids'][0][0] * 0.99)
    priceJpyBtc = (
        bitbankJpy['asks'][0][0] * 1.01 if doTrade == -1 else
        bitbankJpy['bids'][0][0] * 0.99)
    priceXrpBtc = (
        hitbtc2['bids'][0][0] * 0.99 if doTrade == -1 else
        hitbtc2['asks'][0][0] * 1.01)
    print('tradeChance{} {}XRP {} {} {} diff{}'.format(
        doTrade, val, priceXrpJpy, priceJpyBtc, priceXrpBtc,
        doTrade * (priceXrpBtc - priceXrpJpy * priceJpyBtc)))
    if val < minUnit:
        return capacity
    # TODO 売買量をいじって偏りをなおす
    if doTrade == 1:  # 2回売る
        if not production:
            print('sell bitbank XRP/JPY {}'.format(val))
            print('buy bitbank BTC/JPY {}'.format(
                val / bitbankXrp['asks'][-1][0]))
            print('buy hitbtc2 XRP/BTC {}'.format(val))
        else:
            # TODO production
            el = asyncio.get_event_loop()
            el
    elif doTrade == -1:  # 2回買う
        if not production:
            print('buy bitbank XRP/JPY {}'.format(val))
            print('sell bitbank BTC/JPY {}'.format(
                val / bitbankXrp['asks'][-1][0]))
            print('sell hitbtc2 XRP/BTC {}'.format(val))
        else:
            # TODO
            el = asyncio.get_event_loop()
            el
    return fetchCapacity(inited)


# 1: BASE2/BASE1, 2: ALT/BASE2, 3: ALT/BASE1
def calcBuyingTwice(ask1, ask2, bid3, threshold):
    """ALT -> BASE1がBASE1 -> BASE2 -> ALTを上回れば(比率, 量)を返す."""
    idx = np.zeros(3).astype(int)

    amount1 = np.cumsum(ask1[:, 1] / ask2[-1][0])
    amount2 = np.cumsum(ask2[:, 1])
    amount3 = np.cumsum(bid3[:, 1])

    ratio = bid3[:, 0][idx[2]] / (ask1[:, 0][idx[0]] * ask2[:, 0][idx[1]])
    if ratio < threshold:
        return (ratio, 0)
    value = np.min([amount1[idx[0]], amount2[idx[1]], amount3[idx[2]]])

    for i in range(9):
        idx[np.argmin([
            amount1[idx[0]], amount2[idx[1]], amount3[idx[2]]])] += 1
        new_ratio = (
            bid3[:, 0][idx[2]] / (ask1[:, 0][idx[0]] * ask2[:, 0][idx[1]]))
        if new_ratio < threshold:
            break
        ratio = new_ratio
        value = np.min([amount1[idx[0]], amount2[idx[1]], amount3[idx[2]]])
    return ratio, value


def calcSellingTwice(bid1, bid2, ask3, threshold):
    """ALT -> BASE2 -> BASE1がBASE1 -> ALTを上回れば(比率, 量)を返す."""
    idx = np.zeros(3).astype(int)

    amount1 = np.cumsum(bid1[:, 1] / bid2[-1][0])
    amount2 = np.cumsum(bid2[:, 1])
    amount3 = np.cumsum(ask3[:, 1])

    ratio = bid1[:, 0][idx[0]] * bid2[:, 0][idx[1]] / ask3[:, 0][idx[2]]
    if ratio < threshold:
        return (ratio, 0)
    value = np.min([amount1[idx[0]], amount2[idx[1]], amount3[idx[2]]])

    for i in range(9):
        idx[np.argmin([
            amount1[idx[0]], amount2[idx[1]], amount3[idx[2]]])] += 1
        new_ratio = (
            bid1[:, 0][idx[0]] * bid2[:, 0][idx[1]] / ask3[:, 0][idx[2]])
        if new_ratio < threshold:
            break
        ratio = new_ratio
        value = np.min([amount1[idx[0]], amount2[idx[1]], amount3[idx[2]]])
    return ratio, value


def fetchCapacity(inited):
    """余力取得."""
    el = asyncio.get_event_loop()
    cap = el.run_until_complete(asyncio.gather(
        inited['hitbtc2'].fetch_balance(),
        inited['bitbank'].fetch_balance()))
    newCap = {'hitbtc2': cap[0]['free'], 'bitbank': cap[1]['free']}
    return newCap


def fetchValue(inited):
    """価格と売買可能量取得."""
    def f(dic, ident, symbol):
        return dic[ident].fetch_order_book(symbol)
    el = asyncio.get_event_loop()
    val = el.run_until_complete(asyncio.gather(
        inited['hitbtc2'].fetch_order_book('XRP/BTC', limit=10),
        inited['bitbank'].fetch_order_book('XRP/JPY', limit=10),
        inited['bitbank'].fetch_order_book('BTC/JPY', limit=10)))
    newVal = {
        'hitbtc2': {'XRP/BTC': val[0]},
        'bitbank': {'XRP/JPY': val[1], 'BTC/JPY': val[2]}}
    return newVal


if __name__ == "__main__":
    exit(main())

# vim:fenc=utf-8 ff=unix ft=python ts=4 sw=4 sts=4 fdm=indent fdl=0 fdn=1:
# vim: si et cinw=if,elif,else,for,while,try,except,finally,def,class:
