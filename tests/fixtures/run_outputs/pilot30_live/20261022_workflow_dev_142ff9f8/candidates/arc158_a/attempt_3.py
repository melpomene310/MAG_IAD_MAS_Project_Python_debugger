import sys

readline = sys.stdin.readline


def solve(L):
    s = sum(L)
    if s % 3:
        return -1

    num = s // 3
    tmp1 = 0
    tmp2 = 0

    for x in L:
        if (x - num) % 2:
            return -1
        if x < num:
            tmp1 += (num - x) // 2
        else:
            tmp2 += (x - num) // 2

    if tmp1 == tmp2:
        return tmp1
    return -1


T = int(readline())
for _ in range(T):
    L = list(map(int, readline().split()))
    print(solve(L))
