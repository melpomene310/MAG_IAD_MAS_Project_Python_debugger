import sys, heapq
def main():
    data = sys.stdin.buffer.read().split()
    N = int(data[0]); M = int(data[1])
    graph = [[] for _ in range(N)]
    indeg = [0]*N
    pairs = set()
    idx = 2
    for _ in range(M):
        u = int(data[idx])-1; v = int(data[idx+1])-1; idx += 2
        key = u*N + v
        if key in pairs:
            continue
        pairs.add(key)
        graph[u].append(v)
        indeg[v] += 1
    que = [i for i in range(N) if indeg[i]==0]
    heapq.heapify(que)
    answers = []
    while que:
        now = heapq.heappop(que)
        answers.append(now+1)
        for to in graph[now]:
            indeg[to] -= 1
            if indeg[to]==0:
                heapq.heappush(que, to)
    if len(answers)==N:
        sys.stdout.write(' '.join(map(str,answers)))
    else:
        sys.stdout.write('-1')
main()
