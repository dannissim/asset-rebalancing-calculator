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
SECONDS_TO_WAIT_BETWEEN_API_CALLS = 0.5
JSON_INDENT = 2
PRICE_ROUTE = '/quote/{symbol}'
PRICE_KEY = 'price'
ONE_DOLLAR = 1


class Input(pydantic.BaseModel):
    target_allocation: typing.Dict[str, float]
    deposit_amount: float
    current_holdings: typing.Dict[str, float]

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
    standardize_input(user_input)
    asset_prices = await _get_all_prices(user_input.current_holdings.keys())
    current_market_value = {
        asset: asset_prices[asset] * user_input.current_holdings[asset]
        for asset in asset_prices
    }
    market_value_difference = _get_market_value_difference(current_market_value, user_input)
    amount_to_purchase = _get_amount_to_purchase(market_value_difference, user_input.deposit_amount,
                                                 asset_prices)
    result = Result(current_allocation=_get_current_allocation(current_market_value),
                    new_allocation=_get_new_allocation(user_input, asset_prices,
                                                       amount_to_purchase),
                    amount_to_purchase=amount_to_purchase)
    OUTPUT_FILE_PATH.write_text(json.dumps(result.dict(), indent=JSON_INDENT))


def standardize_input(user_input: Input):
    for asset in user_input.current_holdings:
        if asset not in user_input.target_allocation:
            user_input.target_allocation[asset] = 0
        if asset not in user_input.leveraged_assets:
            user_input.leveraged_assets[asset] = 1
    for asset in user_input.target_allocation:
        if asset not in user_input.current_holdings:
            user_input.current_holdings[asset] = 0
        if asset not in user_input.leveraged_assets:
            user_input.leveraged_assets[asset] = 1
    if CASH not in user_input.current_holdings:
        user_input.current_holdings[CASH] = 0
    if CASH not in user_input.target_allocation:
        user_input.target_allocation[CASH] = 0


async def _get_all_prices(assets: typing.Iterable[str]) -> typing.Dict[str, float]:
    prices = dict()
    assets_without_cash = [asset for asset in assets if asset != CASH]
    async with httpx.AsyncClient(base_url=FMP_API_URL) as fmp_client:
        for asset in assets_without_cash:
            raw_response = await fmp_client.get(PRICE_ROUTE.format(symbol=asset.upper()),
                                                params=API_KEY_PARAM)
            raw_response.raise_for_status()
            prices[asset] = raw_response.json()[0][PRICE_KEY]
            # the free API has a rate limit
            await asyncio.sleep(SECONDS_TO_WAIT_BETWEEN_API_CALLS)
    prices[CASH] = ONE_DOLLAR
    return prices


def _get_market_value_difference(current_market_value: typing.Dict[str, float],
                                 user_input: Input) -> typing.Dict[str, float]:
    new_total_market_value = sum(current_market_value.values()) + user_input.deposit_amount
    irrelevant_assets_market_value = sum(current_market_value[asset]
                                         for asset in current_market_value
                                         if user_input.target_allocation[asset] == 0)
    total_market_value_of_relevant_assets = \
        new_total_market_value - irrelevant_assets_market_value + \
        (user_input.target_allocation[CASH] / HUNDRED_PERCENT) * irrelevant_assets_market_value

    target_market_value = {
        asset: total_market_value_of_relevant_assets * target_allocation / HUNDRED_PERCENT
        for asset, target_allocation in user_input.target_allocation.items()
    }
    target_market_value[CASH] = \
        new_total_market_value * user_input.target_allocation[CASH] / HUNDRED_PERCENT
    return {
        asset: target_market_value[asset] - current_market_value[asset]
        for asset in current_market_value
    }


def _get_amount_to_purchase(market_value_difference: typing.Dict[str, float], deposit_amount: float,
                            asset_prices: typing.Dict[str, float]) -> typing.Dict[str, int]:
    amount_to_purchase = dict()
    available_cash = deposit_amount
    if market_value_difference[CASH] < 0:
        amount_to_purchase[CASH] = int(market_value_difference[CASH])
        available_cash -= int(market_value_difference[CASH])
    for asset in sorted(market_value_difference, key=market_value_difference.get, reverse=True):
        if market_value_difference[asset] < 0:
            if asset == CASH:
                continue
            amount_to_purchase[asset] = 0
            continue
        amount_of_units_to_purchase = int(
            min(available_cash, market_value_difference[asset]) / asset_prices[asset])
        market_value_of_units_to_purchase = amount_of_units_to_purchase * asset_prices[asset]
        available_cash -= market_value_of_units_to_purchase
        amount_to_purchase[asset] = amount_of_units_to_purchase
    amount_to_purchase[CASH] += int(available_cash)
    return amount_to_purchase


def _get_current_allocation(
        current_market_value: typing.Dict[str, float]) -> typing.Dict[str, float]:
    total_market_value = sum(current_market_value.values())
    current_allocation = dict()
    for asset in current_market_value:
        current_allocation_of_asset = round(
            HUNDRED_PERCENT * current_market_value[asset] / total_market_value, ROUND_PRECISION)
        current_allocation[asset] = current_allocation_of_asset
    return current_allocation


def _get_new_allocation(user_input: Input, asset_prices: typing.Dict[str, float],
                        amount_to_purchase: typing.Dict[str, int]) -> typing.Dict[str, float]:
    new_allocation = dict()
    new_total_market_value = sum(
        asset_prices[asset] * user_input.current_holdings[asset]
        for asset in user_input.current_holdings) + user_input.deposit_amount
    for asset in user_input.current_holdings:
        new_market_value = (user_input.current_holdings[asset] +
                            amount_to_purchase[asset]) * asset_prices[asset]
        new_proportion = new_market_value / new_total_market_value
        new_allocation[asset] = round(HUNDRED_PERCENT * new_proportion, ROUND_PRECISION)
    return new_allocation
