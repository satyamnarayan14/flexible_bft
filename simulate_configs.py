# simulate_configs.py
# Pre-defined simulation scenarios
def config_basic():
    return {
        "n": 7,
        "f": 2,
        "byzantine": [],   # list of node indices that are Byzantine
        "abc": [],         # list of node indices that are ABC
        "drop_rate": 0.0,
        "min_delay": 0.01,
        "max_delay": 0.04
    }

def config_byzantine_one():
    c = config_basic()
    c["byzantine"] = [1]  # node index 1 is byzantine equivocator
    return c

def config_byzantine_two():
    c = config_basic()
    c["byzantine"] = [1,2]
    return c
