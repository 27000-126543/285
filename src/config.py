import os
import yaml

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'settings.yaml')
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    for key, value in os.environ.items():
        if key.startswith('FUND_POOL_'):
            _set_nested_config(config, key[10:].lower(), value)
    
    return config

def _set_nested_config(config, key_path, value):
    keys = key_path.split('_')
    current = config
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value

CONFIG = load_config()
