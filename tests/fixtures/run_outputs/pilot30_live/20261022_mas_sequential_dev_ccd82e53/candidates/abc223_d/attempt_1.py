import heapq
import sys

def main():
    data = sys.stdin.buffer.read().split()
    if not data:
        return
    it = iter(data)
    N = int(next(it))
    M = int(next(it))

    graph = [[] for _ in range(N)]
    indeg = [0] * N
    pairs = set()

    for _ in range(M):
        u = int(next(it)) - 1
        v = int(next(it)) - 1
        pair = (u, v)
        if pair in pairs:
            continue
        pairs.add(pair)
        graph[u].append(v)
        indeg[v] += 1

    que = [i for i in range(N) if indeg[i] == 0]
    heapq.heapify(que)

    answers = []
    while que:
        now = heapq.heappop(que)
        answers.append(now + 1)
        for to in graph[now]:
            indeg[to] -= 1
            if indeg[to] == 0:
                heapq.heappush(que, to)

    if len(answers) == N:
        sys.stdout.write(' '.join(map(str, answers)) + '\n')
    else:
        sys.stdout.write('-1\n')

main()
