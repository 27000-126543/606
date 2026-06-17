import urllib.request
import json
import urllib.error


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


def get(url, token):
    req = urllib.request.Request(
        url, method="GET",
        headers={"Authorization": f"Bearer {token}"}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode()), None
    except urllib.error.HTTPError as e:
        return None, (e.code, json.loads(e.read().decode()))


def post(url, token, data=None):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = json.dumps(data).encode() if data else b"{}"
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode()), None
    except urllib.error.HTTPError as e:
        return None, (e.code, json.loads(e.read().decode()))


admin_token = login("admin", "Admin@123456")

print("=" * 60)
print("测试日报和根因分析")
print("=" * 60)

# 获取一个异常ID
anomalies, _ = get("http://localhost:8000/api/v1/anomalies?page_size=1", admin_token)
anomaly_id = anomalies["data"][0]["id"]
print(f"\n测试用异常ID: {anomaly_id}")

print("\n--- 1. 根因分析测试 ---")
result, err = post(f"http://localhost:8000/api/v1/anomalies/{anomaly_id}/analyze", admin_token)
if err:
    print(f"❌ {err[0]}: {err[1].get('detail', err[1])}")
else:
    print(f"✅ 成功")
    print(f"  响应结构: {list(result.keys())}")
    if "data" in result:
        data = result["data"]
        if isinstance(data, dict):
            print(f"  data keys: {list(data.keys())}")
            if "candidate_root_causes" in data:
                print(f"  候选根因数量: {len(data['candidate_root_causes'])}")
            if "impact_chain" in data:
                print(f"  影响链路数量: {len(data.get('impact_chain', []))}")
            if "recommended_teams" in data:
                print(f"  推荐团队数量: {len(data.get('recommended_teams', []))}")
        else:
            print(f"  data类型: {type(data)}")
            print(f"  data内容: {str(data)[:200]}")

print("\n--- 2. 生成日报 ---")
result, err = post("http://localhost:8000/api/v1/query/reports/daily/generate", admin_token)
if err:
    print(f"❌ {err[0]}: {err[1].get('detail', err[1])}")
else:
    print(f"✅ 成功")
    print(f"  结果: {json.dumps(result, ensure_ascii=False, indent=2)[:300]}")

print("\n--- 3. 日报列表 ---")
result, err = get("http://localhost:8000/api/v1/query/reports/daily", admin_token)
if err:
    print(f"❌ {err[0]}: {err[1].get('detail', err[1])}")
else:
    print(f"✅ 成功")
    print(f"  total: {result.get('total', 'N/A')}")
    if result.get("data"):
        report = result["data"][0]
        report_id = report.get("id")
        print(f"  最新报表ID: {report_id}")
        print(f"  报表日期: {report.get('report_date')}")
        
        # 测试报表详情
        print("\n--- 4. 日报详情 ---")
        detail, err2 = get(f"http://localhost:8000/api/v1/query/reports/{report_id}", admin_token)
        if err2:
            print(f"❌ {err2[0]}: {err2[1].get('detail', err2[1])}")
        else:
            print(f"✅ 成功")
            data = detail.get("data", {})
            print(f"  异常总数: {data.get('total_anomalies')}")
            print(f"  平均修复时长: {data.get('avg_resolution_minutes')} 分钟")
            print(f"  重复率: {data.get('repeat_rate')}")
            print(f"  影响范围: {data.get('impact_scope_breakdown')}")

print("\n" + "=" * 60)
