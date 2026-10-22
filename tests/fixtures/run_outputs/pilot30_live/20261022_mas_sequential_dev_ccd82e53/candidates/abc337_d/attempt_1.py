import sys

def main():
    input_data = sys.stdin.buffer.read().split()
    H = int(input_data[0])
    W = int(input_data[1])
    K = int(input_data[2])
    S = [input_data[3 + i].decode() for i in range(H)]

    ans = 10**10

    # Horizontal windows
    if W >= K:
        for i in range(H):
            row = S[i]
            chk = [0, 0, 0]
            for j in range(K):
                c = row[j]
                if c == 'o':
                    chk[0] += 1
                elif c == 'x':
                    chk[1] += 1
                else:
                    chk[2] += 1
            if chk[1] == 0:
                if chk[2] < ans:
                    ans = chk[2]
            for j in range(K, W):
                c = row[j - K]
                if c == 'o':
                    chk[0] -= 1
                elif c == 'x':
                    chk[1] -= 1
                else:
                    chk[2] -= 1
                c = row[j]
                if c == 'o':
                    chk[0] += 1
                elif c == 'x':
                    chk[1] += 1
                else:
                    chk[2] += 1
                if chk[1] == 0:
                    if chk[2] < ans:
                        ans = chk[2]

    # Vertical windows
    if H >= K:
        for j in range(W):
            chk = [0, 0, 0]
            for i in range(K):
                c = S[i][j]
                if c == 'o':
                    chk[0] += 1
                elif c == 'x':
                    chk[1] += 1
                else:
                    chk[2] += 1
            if chk[1] == 0:
                if chk[2] < ans:
                    ans = chk[2]
            for i in range(K, H):
                c = S[i - K][j]
                if c == 'o':
                    chk[0] -= 1
                elif c == 'x':
                    chk[1] -= 1
                else:
                    chk[2] -= 1
                c = S[i][j]
                if c == 'o':
                    chk[0] += 1
                elif c == 'x':
                    chk[1] += 1
                else:
                    chk[2] += 1
                if chk[1] == 0:
                    if chk[2] < ans:
                        ans = chk[2]

    print(-1 if ans == 10**10 else ans)

main()
