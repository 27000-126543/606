import urllib.request
import urllib.error

# 测试健康检查
try:
    req = urllib.request.Request("http://localhost:8000/health")
    with urllib.request.urlopen(req) as resp:
        print(f"/health: {resp.status}")
        print(resp.read().decode())
except Exception as e:
    print(f"/health 失败: {e}")

print()

# 测试 docs
try:
    req = urllib.request.Request("http://localhost:8000/docs")
    with urllib.request.urlopen(req) as resp:
        print(f"/docs: {resp.status}")
except Exception as e:
    print(f"/docs 失败: {e}")

print()

# 测试登录
try:
    import json
    data = json.dumps({"username": "admin", "password": "Admin@123456"}).encode()
    req = urllib.request.Request(
        "http://localhost:8000/api/v1/auth/login",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        print(f"/api/v1/auth/login: {resp.status}")
        result = json.loads(resp.read().decode())
        print(f"  message: {result.get('message')}")
except Exception as e:
    print(f"/api/v1/auth/login 失败: {e}")

print()

# 测试工单列表
try:
    import json
    # 先登录
    data = json.dumps({"username": "admin", "password": "Admin@123456"}).encode()
    req = urllib.request.Request(
        "http://localhost:8000/api/v1/auth/login",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode())
        token = result["data"]["access_token"]
    
    req = urllib.request.Request(
        "http://localhost:8000/api/v1/work-orders?page_size=1",
        headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req) as resp:
        print(f"/api/v1/work-orders: {resp.status}")
        result = json.loads(resp.read().decode())
        print(f"  total: {result.get('total')}")
except Exception as e:
    print(f"/api/v1/work-orders 失败: {e}")

print()

# 测试预案执行
try:
    req = urllib.request.Request(
        "http://localhost:8000/api/v1/playbooks/execute",
        data=b"{}",
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        print(f"/api/v1/playbooks/execute: {resp.status}")
except urllib.error.HTTPError as e:
    print(f"/api/v1/playbooks/execute: {e.code}")
    print(e.read().decode()[:300])
except Exception as e:
    print(f"/api/v1/playbooks/execute 失败: {e}")
