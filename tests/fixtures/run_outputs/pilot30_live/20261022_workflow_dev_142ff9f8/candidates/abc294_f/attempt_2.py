import sys

def main():
    data = sys.stdin.buffer.read().split()
    idx = 0
    n = int(data[idx]); idx += 1
    m = int(data[idx]); idx += 1
    k = int(data[idx]); idx += 1

    nums1 = []
    for i in range(n):
        a = int(data[idx]); idx += 1
        b = int(data[idx]); idx += 1
        nums1.append((a, a + b))
    nums2 = []
    for i in range(m):
        a = int(data[idx]); idx += 1
        b = int(data[idx]); idx += 1
        nums2.append((a, a + b))

    l = 0.0
    r = 1.0

    for _ in range(50):
        mid = (l + r) / 2

        temp1 = [a - s * mid for (a, s) in nums1]
        temp2 = [a - s * mid for (a, s) in nums2]
        temp2.sort()

        count = 0
        for i in range(n):
            ng = -1
            ok = m
            while (ok - ng) > 1:
                mid2 = (ng + ok) // 2
                if temp2[mid2] + temp1[i] >= 0:
                    ok = mid2
                else:
                    ng = mid2
            count += m - ok

        if count >= k:
            l = mid
        else:
            r = mid

    print(l * 100)

main()
