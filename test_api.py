import urllib.request
import json

r = urllib.request.urlopen('http://localhost:8000/openapi.json')
data = json.loads(r.read().decode())

print('Available endpoints:')
for path, methods in sorted(data.get('paths', {}).items()):
    for method in methods.keys():
        print(f'  {method.upper():6s} {path}')

print(f'\nTotal: {len(data.get("paths", {}))} paths')
