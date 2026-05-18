"""Backend startup script — forces SelectorEventLoop on Windows, auto-restarts on crash."""
import asyncio
import subprocess
import sys
import os
import time

# Set SelectorEventLoop policy before any asyncio usage so ALL loops (including uvicorn's
# internal asyncio_loop_factory) use SelectorEventLoop instead of ProactorEventLoop (IOCP).
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

_PORT = int(os.environ.get('BACKEND_PORT', '8001'))
_RESTART_DELAY = 0.5


def _run_once():
    import uvicorn
    uvicorn.run(
        'backend.app.main:app',
        host='0.0.0.0',
        port=_PORT,
    )


if __name__ == '__main__':
    if '--worker' in sys.argv:
        _run_once()
    else:
        script = os.path.abspath(__file__)
        env = {**os.environ, 'BACKEND_PORT': str(_PORT)}
        attempt = 0
        while True:
            attempt += 1
            print(f'[supervisor] Starting backend attempt {attempt} on port {_PORT}', flush=True)
            result = subprocess.run([sys.executable, script, '--worker'], env=env)
            if result.returncode == 0:
                print('[supervisor] Backend exited cleanly.', flush=True)
                break
            print(f'[supervisor] Backend crashed (exit={result.returncode}), restarting in {_RESTART_DELAY}s...', flush=True)
            time.sleep(_RESTART_DELAY)
