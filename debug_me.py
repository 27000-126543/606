import urllib.request
import json


def login(username, password):
    url = "http://localhost:8000/api/v1/auth/login"
    data = json.dumps({"username": username, "password": password}).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode())
        return result["data"]["access_token"]


def get_me(token):
    url = "http://localhost:8000/api/v1/auth/me"
    req = urllib.request.Request(
        url, method="GET",
        headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req) as resp:
        data = resp.read().decode()
        print(f"Raw response: {data[:500]}")
        return json.loads(data)


token = login("admin", "Admin@123456")
print("Token obtained")
print()

result = get_me(token)
print()
print(f"Type: {type(result)}")
print(f"Keys: {result.keys() if isinstance(result, dict) else 'N/A'}")
