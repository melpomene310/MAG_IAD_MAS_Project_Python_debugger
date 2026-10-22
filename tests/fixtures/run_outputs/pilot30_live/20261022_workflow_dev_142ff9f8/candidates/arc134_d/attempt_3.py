if A[i] < bottom or (A[i] == bottom and ok == 1):
    ans.append(i)
    if ok == 0:
        if A[ans[-1]+N] < A[i+N]:
            ok = 1
        elif A[ans[-1]+N] > A[i+N]:
            ok = -1
