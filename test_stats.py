import requests
import json

BASE_URL = "http://localhost:8000"

def login(username, password):
    response = requests.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"username": username, "password": password}
    )
    print(f"登录 {username} 状态码: {response.status_code}")
    if response.status_code == 200:
        return response.json()["data"]["access_token"]
    print(f"错误: {response.text}")
    return None

def get_system_stats(token):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{BASE_URL}/api/v1/query/system/stats", headers=headers)
    print(f"\n=== 系统统计 ===")
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(f"错误: {response.text}")
    return response

if __name__ == "__main__":
    for user, pwd in [("supervisor1", "Super@123"), ("operator1", "Oper@123")]:
        token = login(user, pwd)
        if token:
            get_system_stats(token)
