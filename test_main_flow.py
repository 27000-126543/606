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
        return json.loads(resp.read().decode())


def get_anomalies(token, page=1, page_size=10):
    url = f"http://localhost:8000/api/v1/anomalies?page={page}&page_size={page_size}"
    req = urllib.request.Request(
        url, method="GET",
        headers={"Authorization": f"Bearer {token}"}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode()), None
    except urllib.error.HTTPError as e:
        err = json.loads(e.read().decode())
        return None, err


def get_work_orders(token, page=1, page_size=10):
    url = f"http://localhost:8000/api/v1/work-orders?page={page}&page_size={page_size}"
    req = urllib.request.Request(
        url, method="GET",
        headers={"Authorization": f"Bearer {token}"}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode()), None
    except urllib.error.HTTPError as e:
        err = json.loads(e.read().decode())
        return None, err


print("=" * 60)
print("测试认证链和主链路接口")
print("=" * 60)

print("\n1. 登录获取 token...")
admin_token = login("admin", "Admin@123456")
operator_token = login("operator1", "Oper@123")
print("   ✅ 两个账号都获取到 token")

print("\n2. 测试 /auth/me (admin)...")
me = get_me(admin_token)
print(f"   用户: {me['data']['username']}")
print(f"   角色: {me['data']['role']}")
print(f"   姓名: {me['data']['real_name']}")

print("\n3. 测试异常列表 (admin 主管账号)...")
result, err = get_anomalies(admin_token)
if err:
    print(f"   ❌ 失败: {err.get('detail', err)}")
else:
    print(f"   ✅ 成功")
    print(f"   总数: {result['total']} 条")
    print(f"   当前页: {len(result['data'])} 条")
    if result['data']:
        print(f"   第一条: {result['data'][0]['title'][:40]}...")

print("\n4. 测试工单列表 (admin 主管账号)...")
result, err = get_work_orders(admin_token)
if err:
    print(f"   ❌ 失败: {err.get('detail', err)}")
else:
    print(f"   ✅ 成功")
    print(f"   总数: {result['total']} 条")
    print(f"   当前页: {len(result['data'])} 条")
    if result['data']:
        print(f"   第一条: {result['data'][0]['title'][:40]}...")

print("\n5. 测试异常列表 (operator1 运维账号)...")
result, err = get_anomalies(operator_token)
if err:
    print(f"   ❌ 失败: {err.get('detail', err)}")
else:
    print(f"   ✅ 成功")
    print(f"   总数: {result['total']} 条 (应该只看到自己团队的)")
    print(f"   当前页: {len(result['data'])} 条")

print("\n6. 测试工单列表 (operator1 运维账号)...")
result, err = get_work_orders(operator_token)
if err:
    print(f"   ❌ 失败: {err.get('detail', err)}")
else:
    print(f"   ✅ 成功")
    print(f"   总数: {result['total']} 条 (应该只看到自己团队的)")
    print(f"   当前页: {len(result['data'])} 条")

print("\n" + "=" * 60)
