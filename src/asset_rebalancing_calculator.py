import json
import pathlib
import typing

import pydantic

ROOT_DIR = pathlib.Path(__file__).parents[1]
INPUT_FILE_PATH = ROOT_DIR.joinpath('input.json')
OUTPUT_FILE_PATH = ROOT_DIR.joinpath('result.json')


class Input(pydantic.BaseModel):
    target_allocation: typing.Dict[str, int]
    deposit_amount: int
    current_market_value: typing.Dict[str, int]

    @pydantic.validator('target_allocation')
    def must_sum_to_100(cls, target_allocation: typing.Dict[str, int]):
        allocation_sum = sum(target_allocation[asset] for asset in target_allocation)
        if allocation_sum != 100:
            raise ValueError('All of the target allocation percentages must sum up to be 100%.')
        return target_allocation


class Result(pydantic.BaseModel):
    current_allocation: typing.Dict[str, int]
    new_allocation: typing.Dict[str, int]
    amount_to_purchase: typing.Dict[str, int]


async def main():
    user_input = Input.parse_obj(json.loads(INPUT_FILE_PATH.read_text()))
    current_allocation = _calculate_current_allocation(user_input.current_market_value)

    return


async def _calculate_current_allocation(current_market_value: typing.Dict[str, int]):
    total_market_value = sum(current_market_value[asset] for asset in current_market_value)
    current_allocation = dict()
    for asset in current_market_value:
        current_allocation[asset] = round(100 * current_market_value[asset] / total_market_value)
