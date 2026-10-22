# B
n = int(input())
a = list(map(int, input().split()))
call = set()
for i in range(n):
    if i+1 in call:
        pass
    else:
        call.add(a[i])
no_call = []
for i in range(1, n+1):
    if i not in call:
        no_call.append(i)
print(len(no_call))
print(*no_call)
