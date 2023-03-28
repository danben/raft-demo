import asyncio


async def print_loop_time():
    loop = asyncio.get_event_loop()
    print(loop.time())
    await asyncio.sleep(1)
    print(loop.time())

asyncio.run(print_loop_time())
