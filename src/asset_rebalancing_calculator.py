#TODO: check naming
#TODO: check dfs vs bfs design
#TODO: make sure there's typing everywhere & return types
import asyncio
import json
import os
import pathlib
import typing

import httpx
import pydantic

ROOT_DIR = pathlib.Path(__file__).parents[1]
INPUT_FILE_PATH = ROOT_DIR.joinpath('input.json')
OUTPUT_FILE_PATH = ROOT_DIR.joinpath('result.json')
HUNDRED_PERCENT = 100
ROUND_PRECISION = 2
CASH = '_cash'
FMP_API_URL = 'https://financialmodelingprep.com/api/v3'
API_KEY_PARAM = {'apikey': os.environ['API_KEY']}
SECONDS_TO_WAIT_BETWEEN_API_CALLS = 1
JSON_INDENT = 2
MOCK_PRICES = {'schd': 71.26, 'vtv': 131.09, 'upro': 35.575, '_cash': 1}
PRICE_ROUTE = '/quote/{symbol}'
PRICE_KEY = 'price'
ONE_DOLLAR = 1


class Input(pydantic.BaseModel):
    target_allocation: typing.Dict[str, float]
    deposit_amount: float
    current_market_value: typing.Dict[str, float]

    @pydantic.validator('target_allocation')
    def must_sum_to_100(cls, target_allocation: typing.Dict[str, float]):
        allocation_sum = sum(target_allocation.values())
        if allocation_sum != HUNDRED_PERCENT:
            raise ValueError('All of the target allocation percentages must sum up to be 100%.')
        return target_allocation


class Result(pydantic.BaseModel):
    current_allocation: typing.Dict[str, float]
    new_allocation: typing.Dict[str, float]
    amount_to_purchase: typing.Dict[str, int]


async def main():
    user_input = Input.parse_obj(json.loads(INPUT_FILE_PATH.read_text()))
    market_value_difference = _get_market_value_difference(user_input)
    # asset_prices = await _get_all_prices(assets)
    asset_prices = MOCK_PRICES
    amount_to_purchase = _get_amount_to_purchase(market_value_difference, user_input.deposit_amount,
                                                 asset_prices)
    result = Result(current_allocation=_get_current_allocation(user_input.current_market_value),
                    new_allocation=_get_new_allocation(user_input, asset_prices,
                                                       amount_to_purchase),
                    amount_to_purchase=amount_to_purchase)
    OUTPUT_FILE_PATH.write_text(json.dumps(result.dict(), indent=JSON_INDENT))


def _get_market_value_difference(user_input: Input) -> typing.Dict[str, float]:
    new_total_market_value = _get_new_total_market_value(user_input)
    target_market_value = {
        asset: new_total_market_value * target_allocation / HUNDRED_PERCENT
        for asset, target_allocation in user_input.target_allocation.items()
    }
    return {
        asset: target_market_value[asset] - user_input.current_market_value[asset]
        for asset in user_input.current_market_value
    }


def _get_new_total_market_value(user_input: Input) -> float:
    return sum(user_input.current_market_value.values()) + user_input.deposit_amount


async def _get_all_prices(assets: typing.Iterable[str]) -> typing.Dict[str, float]:
    prices = dict()
    assets_without_cash = [asset for asset in assets if asset != CASH]
    async with httpx.AsyncClient(base_url=FMP_API_URL) as fmp_client:
        for asset in assets_without_cash:
            raw_response = await fmp_client.get(PRICE_ROUTE.format(symbol=asset),
                                                params=API_KEY_PARAM)
            raw_response.raise_for_status()
            prices[asset] = raw_response.json()[0][PRICE_KEY]
            # the free API has a rate limit
            await asyncio.sleep(SECONDS_TO_WAIT_BETWEEN_API_CALLS)
    prices[CASH] = ONE_DOLLAR  # the price of one dollar is one dollar
    return prices


def _get_amount_to_purchase(market_value_difference: typing.Dict[str, float], deposit_amount: float,
                            asset_prices: typing.Dict[str, float]) -> typing.Dict[str, int]:
    # TODO: make this function shorter & simpler
    amount_to_purchase = dict()
    if market_value_difference[CASH] < 0:
        amount_to_purchase[CASH] = market_value_difference[CASH]
        available_cash = int(deposit_amount - market_value_difference[CASH])
    else:
        available_cash = deposit_amount
    assets_without_cash = [asset for asset in market_value_difference if asset != CASH]
    for asset in sorted(assets_without_cash, key=market_value_difference.get, reverse=True):
        if market_value_difference[asset] < 0:
            # TODO: rename amount_to_invest
            amount_to_invest = 0
            amount_of_stocks = 0
        else:
            amount_of_stocks = int(
                min(available_cash, market_value_difference[asset]) / asset_prices[asset])
            amount_to_invest = amount_of_stocks * asset_prices[asset]
        available_cash -= amount_to_invest
        amount_to_purchase[asset] = amount_of_stocks
    amount_to_purchase[CASH] += available_cash
    return amount_to_purchase


def _get_current_allocation(
        current_market_value: typing.Dict[str, float]) -> typing.Dict[str, float]:
    total_market_value = sum(current_market_value.values())
    return {
        asset: round(HUNDRED_PERCENT * current_market_value[asset] / total_market_value,
                     ROUND_PRECISION)
        for asset in current_market_value
    }


def _get_new_allocation(user_input: Input, asset_prices: typing.Dict[str, float],
                        amount_to_purchase: typing.Dict[str, int]) -> typing.Dict[str, float]:
    new_allocation = dict()
    for asset in user_input.current_market_value:
        new_market_value = (user_input.current_market_value[asset] +
                            amount_to_purchase[asset] * asset_prices[asset])
        new_proportion = new_market_value / _get_new_total_market_value(user_input)
        new_allocation[asset] = round(HUNDRED_PERCENT * new_proportion, ROUND_PRECISION)
    return new_allocation
