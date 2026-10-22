def check(b, c):
    # start at b and end at c-th day, check if everyone is available
    for i in range(N):
        for j in range(b, c + 1):
            if a[i][j] == 'x':
                return False
    return True


a = []
N, D = map(int, input().split())  # N = number of people, D = number of days

for i in range(N):
    s = input()
    a.append(s)

ans = 0
for i in range(D):
    for j in range(i, D):
        # start at i and end at j-th day
        if check(i, j):
            ans = max(ans, j - i + 1)

print(ans)
