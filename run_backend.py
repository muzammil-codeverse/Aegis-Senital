"""Backend startup script that forces SelectorEventLoop on Windows to avoid IOCP proactor crash."""
import asyncio
import sys
import os

if __name__ == '__main__':
    import uvicorn

    # On Windows, uvicorn's asyncio loop factory returns ProactorEventLoop (IOCP) which crashes
    # on Python 3.12 when WebSocket connections are cancelled abruptly. Force SelectorEventLoop.
    loop = asyncio.SelectorEventLoop if sys.platform == 'win32' else 'auto'

    uvicorn.run(
        'backend.app.main:app',
        host='0.0.0.0',
        port=int(os.environ.get('BACKEND_PORT', '8001')),
        loop=loop,
    )
