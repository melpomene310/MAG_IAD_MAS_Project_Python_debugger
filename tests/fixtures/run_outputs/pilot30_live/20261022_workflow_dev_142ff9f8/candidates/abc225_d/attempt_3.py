import sys

def main():
    input = sys.stdin.buffer.readline
    N, Q = map(int, input().split())
    nxt = [-1] * N
    prv = [-1] * N
    head = list(range(N))
    tail = list(range(N))

    out = []
    for _ in range(Q):
        query = list(map(int, input().split()))
        t = query[0]
        x = query[1] - 1
        if t == 1:
            y = query[2] - 1
            nxt[x] = y
            prv[y] = x
            h = head[x]
            tl = tail[y]
            head[tl] = h
            tail[h] = tl
        elif t == 2:
            y = query[2] - 1
            nxt[x] = -1
            prv[y] = -1
            head[y] = y
            tail[x] = x
        else:
            h = head[x]
            res = []
            now = h
            while now != -1:
                res.append(now + 1)
                now = nxt[now]
            out.append(str(len(res)) + " " + " ".join(map(str, res)))
    sys.stdout.write("\n".join(out) + "\n")

main()
