n = int(input())
a = list(map(int, input().split()))
best = a[0]
for i in range(1, n + 1):
    best = max(best, a[i])
print(best)
