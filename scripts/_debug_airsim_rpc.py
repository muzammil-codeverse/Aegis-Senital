"""Debug script to capture actual bytes sent to AirSimNH."""
import msgpack
import msgpackrpc
from tornado.iostream import IOStream

sent_data = []
original_write = IOStream.write


async def capture_write(self, data):
    sent_data.append(bytes(data))
    return await original_write(self, data)


IOStream.write = capture_write

client = msgpackrpc.Client(msgpackrpc.Address("127.0.0.1", 41451), timeout=5)

req = {"camera_name": "front_center", "image_type": 0, "pixels_as_float": False, "compress": False}
try:
    result = client.call("simGetImages", [req], "")
    print("OK:", result)
except Exception as e:
    print("ERROR:", e)

print(f"Sent packets: {len(sent_data)}")
for i, d in enumerate(sent_data):
    try:
        unpacked = msgpack.unpackb(d, raw=False)
        print(f"Packet {i}: {unpacked}")
        if len(unpacked) > 3:
            params = unpacked[3]
            plen = len(params) if hasattr(params, "__len__") else "N/A"
            print(f"  params type={type(params).__name__} len={plen}")
            if hasattr(params, "__iter__"):
                for j, p in enumerate(params):
                    print(f"    param[{j}]: type={type(p).__name__} val={p!r}")
    except Exception as ex:
        print(f"Packet {i} unpack error: {ex}")
        print(f"  raw hex: {d.hex()}")

client.close()
