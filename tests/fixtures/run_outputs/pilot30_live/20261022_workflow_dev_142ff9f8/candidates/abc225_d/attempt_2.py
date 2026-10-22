import sys

def main():
    input = sys.stdin.buffer.readline
    N, Q = map(int, input().split())
    nxt = [-1] * N
    prv = [-1] * N
    parent = list(range(N))

    def find(a):
        root = a
        while parent[root] != root:
            root = parent[root]
        while parent[a] != root:
            parent[a], a = root, parent[a]
        return root

    out = []
    for _ in range(Q):
        query = list(map(int, input().split()))
        t = query[0]
        x = query[1] - 1
        if t == 1:
            y = query[2] - 1
            nxt[x] = y
            prv[y] = x
            parent[find(x)] = find(y)
        elif t == 2:
            y = query[2] - 1
            nxt[x] = -1
            prv[y] = -1
            parent[find(x)] = x
        else:
            head = find(x)
            tail = head
            while nxt[tail] != -1:
                tail = nxt[tail]
            res = []
            now = head
            while now != -1:
                res.append(now + 1)
                now = nxt[now]
            out.append(str(len(res)) + " " + " ".join(map(str, res)))
    sys.stdout.write("\n".join(out) + "\n")

main()
