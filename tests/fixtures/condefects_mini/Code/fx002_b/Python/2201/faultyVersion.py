import sys
import threading


def main():
    n = int(input())
    memo = {}

    def fib(k):
        if k <= 1:
            return 1
        if k in memo:
            return memo[k]
        memo[k] = fib(k - 1) + fib(k - 2)
        return memo[k]

    print(fib(n))


sys.setrecursionlimit(10**6)
threading.stack_size(1 << 26)
threading.Thread(target=main).start()
