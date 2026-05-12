import sys
import os
import subprocess
import argparse

def check_import(name, description=""):
    try:
        mod = __import__(name)
        return "OK", getattr(mod, "__file__", "built-in")
    except ImportError:
        return "WARN (Missing)", None
    except Exception as e:
        return f"WARN (Error: {e})", None

def check_cuda():
    try:
        import torch
        return "OK" if torch.cuda.is_available() else "WARN (No CUDA)"
    except ImportError:
        return "WARN (No torch)"

def check_cmd(cmd):
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return "OK"
    except Exception:
        return "WARN"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="Fail if any warning")
    args = parser.parse_args()

    print("Drone Simulation Dependency Check")
    
    # Python version
    print(f"Python: {sys.version.split(' ')[0]}")
    
    # CUDA
    cuda_status = check_cuda()
    print(f"CUDA: {cuda_status}")

    # AirSim Client Check
    client_status = "WARN (No client found)"
    client_path = None
    
    # 1. Check cosysairsim
    status, path = check_import("cosysairsim")
    if status == "OK":
        client_status = f"OK (cosysairsim)"
        client_path = path
    else:
        # 2. Check airsim
        status, path = check_import("airsim")
        if status == "OK":
            client_status = f"OK (airsim)"
            client_path = path
        else:
            # 3. Check direct path
            pyclient_dir = os.environ.get("AEGIS_COSYS_AIRSIM_PYTHONCLIENT_DIR", r"C:\AegisExternalTools\drone_sim\cosys_airsim\Cosys-AirSim\PythonClient")
            if os.path.exists(pyclient_dir):
                sys.path.insert(0, pyclient_dir)
                status, path = check_import("cosysairsim")
                if status == "OK":
                    client_status = "OK (cosysairsim from sys.path)"
                    client_path = path
                else:
                    status, path = check_import("airsim")
                    if status == "OK":
                        client_status = "OK (airsim from sys.path)"
                        client_path = path

    print(f"Active AirSim Client: {client_status} [{client_path}]")

    # Python packages
    packages = {
        "msgpackrpc": "msgpack-rpc-python",
        "pymavlink": "pymavlink",
        "mavsdk": "mavsdk",
        "geopy": "geopy",
        "pyproj": "pyproj",
        "shapely": "shapely",
        "networkx": "networkx",
        "cv2": "opencv-python"
    }
    
    status_dict = {}
    for mod, pkg in packages.items():
        st, _ = check_import(mod)
        status_dict[mod] = st
        print(f"{mod}: {st}")
    
    geo_status = "OK" if all(status_dict[k] == "OK" for k in ["geopy", "pyproj", "shapely"]) else "WARN"

    print(f"ffmpeg: {check_cmd(['ffmpeg', '-version'])}")
    print(f"git-lfs: {check_cmd(['git', 'lfs', 'version'])}")
    
    ext_dir = os.environ.get("AEGIS_EXTERNAL_TOOLS", r"C:\AegisExternalTools")
    if os.path.exists(ext_dir) and os.path.isdir(ext_dir):
        print("external tools dir: OK")
    else:
        print("external tools dir: WARN")

    cosys_dir = os.environ.get("AEGIS_COSYS_AIRSIM_ROOT", r"C:\AegisExternalTools\drone_sim\cosys_airsim\Cosys-AirSim")
    if os.path.exists(cosys_dir) and os.path.isdir(cosys_dir):
        print("Cosys-AirSim source: OK")
    else:
        print("Cosys-AirSim source: WARN")
        
    has_warn = (
        "WARN" in cuda_status or
        "WARN" in client_status or
        "WARN" in status_dict["msgpackrpc"] or
        "WARN" in status_dict["mavsdk"] or
        "WARN" in status_dict["pymavlink"] or
        "WARN" in geo_status or
        "WARN" in check_cmd(['git', 'lfs', 'version']) or
        not os.path.exists(ext_dir) or
        not os.path.exists(cosys_dir)
    )

    if args.strict and has_warn:
        print("\nStrict mode enabled. Check failed due to warnings.")
        sys.exit(1)
    
    print("\nVerification Passed.")

if __name__ == "__main__":
    main()
