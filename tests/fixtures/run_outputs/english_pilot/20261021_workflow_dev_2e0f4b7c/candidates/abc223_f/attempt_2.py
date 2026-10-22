import sys
def MI(): return map(int, input().split())
INF = 1<<62

def segfunc(x, y):
    return (x[0] + y[0], min(x[1], x[0] + y[1]))

ide_ele = (0, INF)

class SegTree:
    def __init__(self, init_val, segfunc, ide_ele):
        n = len(init_val)
        self.segfunc = segfunc
        self.ide_ele = ide_ele
        self.num = 1 << (n-1).bit_length()
        self.tree = [ide_ele] * 2 * self.num
        for i in range(n):
            self.tree[self.num + i] = init_val[i]
        for i in range(self.num - 1, 0, -1):
            self.tree[i] = self.segfunc(self.tree[2 * i], self.tree[2 * i + 1])
    
    def update(self, k, x):
        k += self.num
        self.tree[k] = x
        while k > 1:
            self.tree[k >> 1] = self.segfunc(self.tree[k & ~1], self.tree[k | 1])
            k >>= 1
    
    def query(self, l, r):
        res_l, res_r = self.ide_ele, self.ide_ele
        l += self.num
        r += self.num
        while l < r:
            if l & 1:
                res_l = self.segfunc(res_l, self.tree[l])
                l += 1
            if r & 1:
                res_r = self.segfunc(self.tree[r - 1], res_r)
            l >>= 1
            r >>= 1
        return self.segfunc(res_l, res_r)
    
    def __getitem__(self, x):
        return self.tree[x + self.num]

N, Q = MI()
S = input()
A = [(1, 1) if s == '(' else (-1, -1) for s in S]

seg = SegTree(A, segfunc, ide_ele)
ans = []
for _ in range(Q):
    q, l, r = MI()
    l -= 1
    r -= 1
    if q == 1:
        a, b = seg[l], seg[r]
        seg.update(l, b)
        seg.update(r, a)
    else:
        a, b = seg.query(l, r + 1)
        ans.append('Yes' if a == 0 and b == 0 else 'No')

sys.stdout.write('\n'.join(ans) + '\n')
