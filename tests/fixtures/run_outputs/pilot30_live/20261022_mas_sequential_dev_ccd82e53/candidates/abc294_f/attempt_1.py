import sys

def main():
    input_data = sys.stdin.buffer.read().split()
    idx = 0
    n = int(input_data[idx]); idx += 1
    m = int(input_data[idx]); idx += 1
    k = int(input_data[idx]); idx += 1

    nums1 = []
    for i in range(n):
        a = int(input_data[idx]); idx += 1
        b = int(input_data[idx]); idx += 1
        nums1.append((a, b))
    nums2 = []
    for i in range(m):
        a = int(input_data[idx]); idx += 1
        b = int(input_data[idx]); idx += 1
        nums2.append((a, b))

    l = 0.0
    r = 1.0

    for _ in range(100):
        mid = (l + r) / 2

        temp1 = [a - (a + b) * mid for (a, b) in nums1]
        temp2 = [a - (a + b) * mid for (a, b) in nums2]
        temp2.sort()

        count = 0
        for i in range(n):
            # count number of j with temp2[j] >= -temp1[i]
            target = -temp1[i]
            # binary search for first index with temp2[idx] >= target
            lo = 0
            hi = m
            while lo < hi:
                mid2 = (lo + hi) // 2
                if temp2[mid2] >= target:
                    hi = mid2
                else:
                    lo = mid2 + 1
            count += m - lo

        if count >= k:
            l = mid
        else:
            r = mid

    print(l * 100)

main()
