import json
from pathlib import Path

import requests


GNS3_SERVER = "http://127.0.0.1:3080/v2"
OUTPUT_FILE = Path(__file__).with_name("local_templates.json")


response = requests.get(f"{GNS3_SERVER}/templates")
response.raise_for_status()
templates = response.json()

with OUTPUT_FILE.open("w", encoding="utf-8") as file:
    json.dump(templates, file, ensure_ascii=False, indent=2)
