import importlib
import sys
import os

client_module = None
pyclient_dir = os.environ.get("AEGIS_COSYS_AIRSIM_PYTHONCLIENT_DIR", r"C:\AegisExternalTools\drone_sim\cosys_airsim\Cosys-AirSim\PythonClient")

# First try normal imports
for name in ("cosysairsim", "airsim"):
    try:
        client_module = importlib.import_module(name)
        print(f"{name} import OK: {getattr(client_module, '__file__', '')}")
        break
    except Exception as exc:
        print(f"{name} import failed: {exc}")

# If failed, try sys.path
if client_module is None and os.path.exists(pyclient_dir):
    sys.path.insert(0, pyclient_dir)
    print(f"Added {pyclient_dir} to sys.path")
    for name in ("cosysairsim", "airsim"):
        try:
            client_module = importlib.import_module(name)
            print(f"{name} import OK from sys.path: {getattr(client_module, '__file__', '')}")
            break
        except Exception as exc:
            print(f"{name} import failed from sys.path: {exc}")

if client_module is None:
    print("No AirSim-compatible Python client available.")
    sys.exit(1)

try:
    client = client_module.MultirotorClient()
    print("MultirotorClient object created.")
    try:
        client.confirmConnection()
        print("Simulator connection OK.")
    except Exception as exc:
        print(f"Client import OK; simulator not running or not reachable: {exc}")
    sys.exit(0)
except Exception as exc:
    print(f"Failed to create MultirotorClient: {exc}")
    sys.exit(1)
