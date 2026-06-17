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
        return None, (e.code, e.read().decode())


def post(url, token, data=None):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = json.dumps(data).encode() if data else b"{}"
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode()), None
    except urllib.error.HTTPError as e:
        return None, (e.code, e.read().decode())


admin_token = login("admin", "Admin@123456")

print("=" * 60)
print("测试日报详情和根因分析")
print("=" * 60)

print("\n--- 1. 日报列表 ---")
result, err = get("http://localhost:8000/api/v1/query/reports/daily?page_size=1", admin_token)
if err:
    print(f"❌ {err[0]}: {err[1][:200]}")
else:
    print(f"✅ 成功，total: {result.get('total')}")
    report = result["data"][0]
    report_id = report["id"]
    print(f"  报表ID: {report_id}")
    print(f"  异常总数: {report.get('total_anomalies')}")
    print(f"  平均修复时长: {report.get('avg_resolution_minutes')}")
    print(f"  重复率: {report.get('repeat_rate')}")

print("\n--- 2. 日报详情 ---")
result, err = get(f"http://localhost:8000/api/v1/query/reports/{report_id}", admin_token)
if err:
    print(f"❌ {err[0]}: {err[1][:200]}")
else:
    print(f"✅ 成功")
    data = result.get("data", {})
    print(f"  report_date: {data.get('report_date')}")
    print(f"  total_anomalies: {data.get('total_anomalies')}")
    print(f"  critical_anomalies: {data.get('critical_anomalies')}")
    print(f"  total_work_orders: {data.get('total_work_orders')}")
    print(f"  avg_resolution_minutes: {data.get('avg_resolution_minutes')}")
    print(f"  repeat_rate: {data.get('repeat_rate')}")
    print(f"  sla_compliance_rate: {data.get('sla_compliance_rate')}")
    print(f"  impact_scope_breakdown keys: {list(data.get('impact_scope_breakdown', {}).keys()) if data.get('impact_scope_breakdown') else 'None'}")

# 获取一个异常ID
anomalies, _ = get("http://localhost:8000/api/v1/anomalies?page_size=1", admin_token)
anomaly_id = anomalies["data"][0]["id"]
print(f"\n测试用异常ID: {anomaly_id}")

print("\n--- 3. 根因分析 ---")
result, err = post(f"http://localhost:8000/api/v1/anomalies/{anomaly_id}/analyze", admin_token)
if err:
    print(f"❌ {err[0]}: {err[1][:500]}")
else:
    print(f"✅ 成功")
    print(f"  响应 keys: {list(result.keys())}")
    data = result.get("data", {})
    if isinstance(data, dict):
        print(f"  data keys: {list(data.keys())}")
        print(f"  candidate_root_causes: {data.get('root_cause_candidates', data.get('candidate_root_causes', 'N/A'))}")
        print(f"  impact_chain: {data.get('dependency_impact_chain', data.get('impact_chain', 'N/A'))}")
        print(f"  recommended_teams: {data.get('recommended_teams', 'N/A')}")
    else:
        print(f"  data: {str(data)[:200]}")

print("\n" + "=" * 60)
