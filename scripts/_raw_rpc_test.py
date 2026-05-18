"""Test what args format AirSimNH actually expects for simGetImages."""
import socket
import msgpack
import time


def connect():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("127.0.0.1", 41451))
    s.settimeout(3)
    return s


def send_recv(sock, data):
    sock.sendall(data)
    buf = b""
    try:
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf += chunk
            try:
                result = msgpack.unpackb(buf, raw=False)
                return result
            except Exception:
                continue
    except socket.timeout:
        pass
    if buf:
        try:
            return msgpack.unpackb(buf, raw=False)
        except Exception:
            return {"raw_hex": buf.hex()}
    return None


def rpc(label, method, *args, msgid=1):
    s = connect()
    msg = msgpack.packb([0, msgid, method, list(args)], use_bin_type=True)
    print(f"\n[{label}]")
    msg_decoded = msgpack.unpackb(msg, raw=False)
    print(f"  Sending: {msg_decoded}")
    print(f"  Params element: {msg_decoded[3]} (len={len(msg_decoded[3])})")
    resp = send_recv(s, msg)
    s.close()
    if resp is not None:
        if isinstance(resp, list) and len(resp) >= 3 and resp[2] is not None:
            print(f"  ERROR: {resp[2]}")
        else:
            print(f"  SUCCESS: {resp}")
    else:
        print("  No response")
    return resp


# Verify ping works
rpc("ping", "ping")

# Try with EXPLICIT 3-element params (to match what server seems to expect)
# Maybe AirSimNH v1.8.1 registers simGetImages with 3 args?
req = {"camera_name": "front_center", "image_type": 0, "pixels_as_float": False, "compress": False}

# 3 args: requests, vehicle_name, external
rpc("3-arg [req, vehicle, external]", "simGetImages", [req], "", False)
rpc("3-arg [req, vehicle, True]", "simGetImages", [req], "", True)
rpc("3-arg [[list-req], vehicle, external]", "simGetImages", [["front_center", 0, False, False]], "", False)

# Check what simGetImages expects by trying 0,1,2,3,4 args
for n in range(5):
    args = [[], "", False, "extra", 0][:n]
    rpc(f"{n}-arg simGetImages", "simGetImages", *args)
