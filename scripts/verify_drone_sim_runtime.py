import sys
import os
import subprocess
import argparse

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

    print("Drone Simulation Runtime Check")

    # 1. Client import
    try:
        import cosysairsim
        print("cosysairsim import: OK")
    except ImportError:
        print("cosysairsim import: WARN (Missing)")
        if args.strict: sys.exit(1)

    # 2. External runtime directory
    ext_dir = os.environ.get("AEGIS_DRONE_SIM_RUNTIME_DIR", r"C:\AegisExternalTools\drone_sim\runtime")
    if os.path.exists(ext_dir) and os.path.isdir(ext_dir):
        print("external runtime directory: OK")
    else:
        print("external runtime directory: WARN")
        if args.strict: sys.exit(1)

    # 3. settings.json
    settings_path = os.path.expandvars(r"%USERPROFILE%\Documents\AirSim\settings.json")
    if os.path.exists(settings_path):
        print("settings.json: OK")
    else:
        print("settings.json: WARN")
        if args.strict: sys.exit(1)

    # 4. Check simulator process / RPC port
    print("Checking RPC port 41451 status...")
    port_status = "WARN"
    try:
        output = subprocess.check_output('netstat -ano | findstr 41451', shell=True).decode()
        if 'LISTENING' in output or 'ESTABLISHED' in output:
            port_status = "OK"
    except Exception:
        pass

    print(f"RPC port 41451: {port_status}")
    if port_status == "WARN":
        if args.strict: 
            print("Simulator not running. Strict mode failed.")
            sys.exit(1)

    # 5. RPC connection and retrieval
    try:
        client = cosysairsim.MultirotorClient()
        client.confirmConnection()
        print("RPC connection: OK")

        try:
            state = client.getMultirotorState()
            print("telemetry retrieval: OK")
        except Exception as e:
            print(f"telemetry retrieval: WARN ({e})")
            if args.strict: sys.exit(1)

        try:
            responses = client.simGetImages([
                cosysairsim.ImageRequest("front_center", cosysairsim.ImageType.Scene, False, False)
            ])
            if responses and responses[0].width > 0:
                print("image retrieval: OK")
            else:
                print("image retrieval: WARN (Empty image)")
                if args.strict: sys.exit(1)
        except Exception as e:
            print(f"image retrieval: WARN ({e})")
            if args.strict: sys.exit(1)

    except Exception as e:
        print(f"RPC connection: WARN ({e})")
        if args.strict:
            print("Failed to connect to simulator in strict mode.")
            sys.exit(1)

    print("Verification Passed.")

if __name__ == "__main__":
    main()
