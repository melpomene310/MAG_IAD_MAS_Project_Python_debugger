import sys

readline = sys.stdin.readline


def solve(L):
    s = sum(L)
    if s % 3:
        return -1

    num = s // 3
    deficit = 0
    excess = 0

    for x in L:
        if x < num:
            deficit += num - x
        elif x > num:
            excess += x - num

    if deficit == excess:
        return deficit
    return -1


T = int(readline())
for _ in range(T):
    L = list(map(int, readline().split()))
    print(solve(L))
