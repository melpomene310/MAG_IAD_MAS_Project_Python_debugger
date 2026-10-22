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

        temp1 = sorted(a - s * mid for (a, s) in nums1)
        temp2 = sorted(a - s * mid for (a, s) in nums2)

        count = 0
        j = m - 1
        for i in range(n):
            while j >= 0 and temp1[i] + temp2[j] >= 0:
                j -= 1
            count += m - 1 - j

        if count >= k:
            l = mid
        else:
            r = mid

    print(l * 100)

main()
