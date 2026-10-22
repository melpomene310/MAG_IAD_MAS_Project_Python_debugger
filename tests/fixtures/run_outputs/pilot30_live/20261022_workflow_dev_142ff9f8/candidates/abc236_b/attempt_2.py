from collections import Counter

N = int(input())
A = list(map(int, input().split()))

cnt = Counter(A)
for v, c in cnt.items():
	if c != 4:
		print(v)
		break
