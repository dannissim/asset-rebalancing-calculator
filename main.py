import asyncio
import pathlib

import dotenv

dotenv.load_dotenv(pathlib.Path(__file__).parent.joinpath('.env'))

from src.asset_rebalancing_calculator import main

if __name__ == '__main__':
    asyncio.run(main())
