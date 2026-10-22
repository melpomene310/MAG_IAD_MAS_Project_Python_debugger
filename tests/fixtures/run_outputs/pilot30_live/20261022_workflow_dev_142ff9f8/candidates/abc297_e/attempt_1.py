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

# Min-heap of (sum, index in A)
heap = [(A[0] + A[0], 0)]
seen = set()
seen.add((0, 0))

ans = None
for _ in range(K):
    x, i = heapq.heappop(heap)
    ans = x
    if i + 1 < N:
        nxt = (A[i + 1] + A[0], i + 1)
        if nxt not in seen:
            seen.add(nxt)
            heapq.heappush(heap, nxt)
    nxt2 = (A[i] + A[1], i)
    if nxt2 not in seen:
        seen.add(nxt2)
        heapq.heappush(heap, nxt2)

print(ans)
