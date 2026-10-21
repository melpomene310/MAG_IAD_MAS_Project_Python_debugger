import sys

def main():
    data = sys.stdin.buffer.read().split()
    if not data:
        return
    H = int(data[0])
    W = int(data[1])
    A = []
    idx = 2
    for _ in range(H):
        row = list(map(int, data[idx:idx + W]))
        idx += W
        A.append(row)

    flag = True
    for h in range(H):
        for i in range(h + 1, H):
            for w in range(W):
                for j in range(w + 1, W):
                    if A[h][w] + A[i][j] > A[i][w] + A[h][j]:
                        flag = False
                        break
                if not flag:
                    break
            if not flag:
                break
        if not flag:
            break

    print("Yes" if flag else "No")

main()
