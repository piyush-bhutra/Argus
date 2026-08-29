from fastapi.testclient import TestClient
from app.main import app
import json

client = TestClient(app)

endpoints = [
    ("POST", "/debate/start", {"claim": "test claim", "rounds": 3}),
    ("GET", "/debate/debate_12345/transcript", None),
    ("GET", "/debate/debate_12345/verdict", None),
    ("GET", "/debate/debate_12345/graph", None)
]

for method, url, body in endpoints:
    if method == "POST":
        r = client.post(url, json=body)
    else:
        r = client.get(url)
    
    print(f"{method} {url} - Status: {r.status_code}")
    print(json.dumps(r.json(), indent=2))
