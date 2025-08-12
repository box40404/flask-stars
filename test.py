import asyncio
from helpers.purchase import process_stars_purchase


async def test():
    await process_stars_purchase(20, 'тест')

asyncio.run(test())