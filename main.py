import asyncio

import dotenv

from src.asset_rebalancing_calculator import main

dotenv.load_dotenv('./.env')

if __name__ == '__main__':
    asyncio.run(main())
