import sys
import bisect

data = sys.stdin.buffer.read().split()
idx = 0
w = int(data[idx]); idx += 1
h = int(data[idx]); idx += 1
n = int(data[idx]); idx += 1
ichigo = []
for _ in range(n):
    x = int(data[idx]); idx += 1
    y = int(data[idx]); idx += 1
    ichigo.append((x, y))
A = int(data[idx]); idx += 1
a = [int(data[idx + i]) for i in range(A)]
idx += A
B = int(data[idx]); idx += 1
b = [int(data[idx + i]) for i in range(B)]
idx += B

ans = {}
for i in range(n):
    s = bisect.bisect(a, ichigo[i][0])
    t = bisect.bisect(b, ichigo[i][1])
    if (s, t) in ans:
        ans[(s, t)] += 1
    else:
        ans[(s, t)] = 1

lis = list(ans.values())

M = max(lis)
if len(ans) == (A + 1) * (B + 1):
    n = min(lis)
else:
    n = 0
print(n, M)
