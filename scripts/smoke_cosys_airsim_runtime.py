import os
import sys
from pathlib import Path
import cosysairsim
import cv2
import numpy as np

out_dir = Path("storage/drone_sim")
out_dir.mkdir(parents=True, exist_ok=True)

try:
    client = cosysairsim.MultirotorClient()
    client.confirmConnection()
except Exception as exc:
    print(f"Client import OK; simulator not running or not reachable: {exc}")
    sys.exit(1)

try:
    state = client.getMultirotorState()
    print("State:", state)
    
    responses = client.simGetImages([
        cosysairsim.ImageRequest("front_center", cosysairsim.ImageType.Scene, False, False)
    ])
    
    if not responses or responses[0].width == 0:
        print("No image returned from simulator.")
        sys.exit(2)
    
    img1d = np.frombuffer(responses[0].image_data_uint8, dtype=np.uint8)
    img = img1d.reshape(responses[0].height, responses[0].width, 3)
    cv2.imwrite(str(out_dir / "smoke_frame.png"), img)
    print("Saved smoke_frame.png")
except Exception as e:
    print(f"Error communicating with simulator: {e}")
    sys.exit(1)

sys.exit(0)
