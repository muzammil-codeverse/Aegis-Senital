TRAIN_CONFIG: dict = {
    "imgsz": 640,
    "batch": 16,
    "epochs": 60,
    "device": "auto",   # "auto" → ultralytics GPU auto-select; override with "cpu" or "0"
    "save_period": 5,   # save checkpoint every N epochs
}

MIN_TRAIN_IMAGES = 500  # hard floor for production datasets
