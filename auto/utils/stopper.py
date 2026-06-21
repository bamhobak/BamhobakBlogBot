import asyncio

_event: asyncio.Event | None = None
_loop: asyncio.AbstractEventLoop | None = None


def init(loop: asyncio.AbstractEventLoop):
    global _event, _loop
    _event = asyncio.Event()
    _loop = loop


def request():
    """어떤 스레드에서도 안전하게 호출 가능 — asyncio 이벤트 루프에 신호 전달"""
    if _loop and _event and not _event.is_set():
        _loop.call_soon_threadsafe(_event.set)


def is_set() -> bool:
    return _event is not None and _event.is_set()


async def sleep(seconds: float):
    """중지 요청 시 즉시 깨어나는 sleep"""
    if _event is None:
        await asyncio.sleep(seconds)
        return
    try:
        await asyncio.wait_for(asyncio.shield(_event.wait()), timeout=seconds)
    except asyncio.TimeoutError:
        pass
