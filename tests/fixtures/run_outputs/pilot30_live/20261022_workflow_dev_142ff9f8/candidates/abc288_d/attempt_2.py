import sys

def main():
    data = sys.stdin.buffer.read().split()
    idx = 0
    N = int(data[idx]); idx += 1
    K = int(data[idx]); idx += 1
    A = data[idx:idx+N]
    idx += N
    Q = int(data[idx]); idx += 1

    S = [[0] for _ in range(K)]
    for i in range(N):
        S[i % K].append(S[i % K][-1] + int(A[i]))

    out = []
    for _ in range(Q):
        l = int(data[idx]) - 1; idx += 1
        r = int(data[idx]) - 1; idx += 1
        s = set()
        for k in range(K):
            s.add(S[k][(r - k) // K + 1] - S[k][(l - k - 1) // K + 1])
        out.append('Yes' if len(s) == 1 else 'No')
    sys.stdout.write('\n'.join(out) + '\n')

main()
