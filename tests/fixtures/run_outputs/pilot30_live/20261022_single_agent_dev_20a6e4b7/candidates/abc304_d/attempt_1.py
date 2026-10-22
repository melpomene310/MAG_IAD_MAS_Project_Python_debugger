import sys
import numpy as np

def main():
    data = sys.stdin.buffer.read().split()
    idx = 0
    w = int(data[idx]); idx+=1
    h = int(data[idx]); idx+=1
    n = int(data[idx]); idx+=1
    arr = np.array(data[idx:idx+2*n], dtype=np.int64)
    idx += 2*n
    xs = arr[0::2]
    ys = arr[1::2]
    A = int(data[idx]); idx+=1
    a = np.array(data[idx:idx+A], dtype=np.int64); idx+=A
    B = int(data[idx]); idx+=1
    b = np.array(data[idx:idx+B], dtype=np.int64); idx+=B

    a.sort()
    b.sort()
    s = np.searchsorted(a, xs, side='right')
    t = np.searchsorted(b, ys, side='right')
    key = s.astype(np.int64)*(B+1) + t
    vals, counts = np.unique(key, return_counts=True)
    M = int(counts.max())
    if len(vals) == (A+1)*(B+1):
        mn = int(counts.min())
    else:
        mn = 0
    print(mn, M)

main()
