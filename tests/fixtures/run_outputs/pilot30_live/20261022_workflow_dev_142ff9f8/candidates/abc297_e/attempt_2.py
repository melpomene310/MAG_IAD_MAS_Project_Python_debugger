import sys
import heapq

input = sys.stdin.readline

def miss():
    return map(int, input().split())

def lmiss():
    return list(map(int, input().split()))

def ii():
    return int(input())

def li():
    return list(input())

N, K = miss()
A = lmiss()
A.sort()

heap = [(A[0] + A[0], 0, 0)]
seen = {(0, 0)}
ans = None

for _ in range(K):
    x, i, j = heapq.heappop(heap)
    ans = x
    if i + 1 <= j and (i + 1, j) not in seen:
        seen.add((i + 1, j))
        heapq.heappush(heap, (A[i + 1] + A[j], i + 1, j))
    if j + 1 < N and (i, j + 1) not in seen:
        seen.add((i, j + 1))
        heapq.heappush(heap, (A[i] + A[j + 1], i, j + 1))

print(ans)
