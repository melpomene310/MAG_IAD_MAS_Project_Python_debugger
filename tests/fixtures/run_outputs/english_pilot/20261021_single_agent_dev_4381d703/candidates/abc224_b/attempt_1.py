H, W = map(int, input().split())
A = [list(map(int, input().split())) for _ in range(H)]

flag = True
for h in range(H-1):
    for w in range(W-1):
        if A[h][w] + A[h+1][w+1] > A[h+1][w] + A[h][w+1]:
            flag = False

print("Yes" if flag else "No")
