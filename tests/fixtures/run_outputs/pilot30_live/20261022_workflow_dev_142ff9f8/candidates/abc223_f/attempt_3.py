import sys
input = sys.stdin.readline

n, q = map(int, input().split())
s = list(input().strip())

size = 1
while size < n:
    size <<= 1

sums = [0] * (2 * size)
mins = [0] * (2 * size)

def val(c):
    return 1 if c == '(' else -1

for i in range(n):
    v = val(s[i])
    sums[size + i] = v
    mins[size + i] = v

for i in range(size - 1, 0, -1):
    l, r = 2 * i, 2 * i + 1
    sums[i] = sums[l] + sums[r]
    mins[i] = min(mins[l], sums[l] + mins[r])

def update(pos, v):
    i = size + pos
    sums[i] = v
    mins[i] = v
    i >>= 1
    while i:
        l, r = 2 * i, 2 * i + 1
        sums[i] = sums[l] + sums[r]
        mins[i] = min(mins[l], sums[l] + mins[r])
        i >>= 1

def query(l, r):
    l += size
    r += size + 1
    left_parts = []
    right_parts = []
    while l < r:
        if l & 1:
            left_parts.append(l)
            l += 1
        if r & 1:
            r -= 1
            right_parts.append(r)
        l >>= 1
        r >>= 1
    total = 0
    mn = 0
    for node in left_parts + right_parts[::-1]:
        total2 = total + sums[node]
        if total + mins[node] < mn:
            mn = total + mins[node]
        total = total2
    return total, mn

out = []
for _ in range(q):
    t, l, r = map(int, input().split())
    l -= 1
    r -= 1
    if t == 2:
        total, mn = query(l, r)
        if total == 0 and mn >= 0:
            out.append("Yes")
        else:
            out.append("No")
    else:
        if l != r:
            s[l], s[r] = s[r], s[l]
            update(l, val(s[l]))
            update(r, val(s[r]))
sys.stdout.write("\n".join(out) + "\n")
