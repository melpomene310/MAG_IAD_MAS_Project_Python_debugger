n = int(input())
if n == 0:
    print(0)
    exit()
total = 0
for i in range(1, n + 1):
    total += i
print(total)
