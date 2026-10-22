import sys
import bisect

data = sys.stdin.buffer.read().split()
idx = 0
w = int(data[idx]); idx += 1
h = int(data[idx]); idx += 1
n = int(data[idx]); idx += 1
xs = [0] * n
ys = [0] * n
for i in range(n):
    xs[i] = int(data[idx]); idx += 1
    ys[i] = int(data[idx]); idx += 1
A = int(data[idx]); idx += 1
a = [int(data[idx + i]) for i in range(A)]
idx += A
B = int(data[idx]); idx += 1
b = [int(data[idx + i]) for i in range(B)]
idx += B

W = B + 1
ans = {}
bisect_a = bisect.bisect
bisect_b = bisect.bisect
for i in range(n):
    s = bisect_a(a, xs[i])
    t = bisect_b(b, ys[i])
    key = s * W + t
    ans[key] = ans.get(key, 0) + 1

lis = list(ans.values())

M = max(lis)
if len(ans) == (A + 1) * (B + 1):
    n = min(lis)
else:
    n = 0
print(n, M)
