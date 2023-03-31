import asyncio

from collections.abc import Coroutine
from datetime import timedelta
from typing import Any, Callable


background_tasks: set[asyncio.Task] = set()


def print_exception(task: asyncio.Task):
    try:
        exc = task.exception()
        if exc is not None:
            print(f"Background task raised exception: {exc}")
    except asyncio.CancelledError:
        pass


def run_in_background(coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
    # Idiomatic recipe for running tasks in the background,
    # as per
    # https://docs.python.org/3/library/asyncio-task.html#creating-tasks.
    # The global set is necessary to avoid garbage collection of unfinished
    # tasks.
    task: asyncio.Task = asyncio.create_task(coro)
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    task.add_done_callback(print_exception)
    return task


def run_every_s(
    f: Callable[..., None],
    cur_time: float,
    duration_s: float,
    stopper: asyncio.Future,
) -> None:
    if not stopper.done():
        loop = asyncio.get_event_loop()
        next_call_time = cur_time + duration_s
        loop.call_at(
            next_call_time, run_every_s, f, next_call_time, duration_s, stopper
        )
        loop.call_soon(f)


def run_every(f: Callable[..., None], duration: timedelta) -> asyncio.Future:
    # Not-super-necessary function to run a coroutine periodically without
    # accumulating clock skew
    loop = asyncio.get_event_loop()
    cur_time = loop.time()
    stopper = loop.create_future()
    run_every_s(f, cur_time, duration.total_seconds(), stopper)
    return stopper


async def test_run_every() -> None:
    def f():
        print(asyncio.get_event_loop().time())

    stopper = run_every(f, timedelta(seconds=1))
    await asyncio.sleep(100)
    stopper.set_result(None)
    await stopper


if __name__ == "__main__":
    asyncio.run(test_run_every())
