import urllib.request
import json


def test_login(username, password):
    url = "http://localhost:8000/api/v1/auth/login"
    data = json.dumps({"username": username, "password": password}).encode()
    req = urllib.request.Request(
        url, 
        data=data, 
        method="POST",
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
            print(f"✅ {username} 登录成功")
            if "data" in result and "access_token" in result["data"]:
                print(f"   Token: {result['data']['access_token'][:60]}...")
            return result
    except urllib.error.HTTPError as e:
        print(f"❌ {username} 登录失败: {e.code}")
        try:
            err = json.loads(e.read().decode())
            print(f"   错误信息: {err.get('detail', err.get('message', err))}")
        except:
            print(f"   响应: {e.read().decode()}")
        return None


print("=" * 60)
print("测试登录接口")
print("=" * 60)

print()
print("1. 测试 admin 账号 (supervisor)")
test_login("admin", "Admin@123456")

print()
print("2. 测试 supervisor1 账号 (supervisor)")
test_login("supervisor1", "Super@123")

print()
print("3. 测试 operator1 账号 (operator)")
test_login("operator1", "Oper@123")

print()
print("4. 测试错误密码")
test_login("admin", "wrongpassword")

print()
print("5. 测试不存在的用户")
test_login("nonexistent", "password")
