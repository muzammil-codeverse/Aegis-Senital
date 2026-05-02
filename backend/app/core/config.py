import json
import os

CONFIGS_DIR = os.path.join(os.path.dirname(__file__), "configs")

VALID_SCENARIOS = ("classroom", "traffic", "security")


def load_scenario_config(scenario: str) -> dict:
    if scenario not in VALID_SCENARIOS:
        raise FileNotFoundError(scenario)
    path = os.path.join(CONFIGS_DIR, f"{scenario}.json")
    with open(path, "r") as f:
        return json.load(f)
