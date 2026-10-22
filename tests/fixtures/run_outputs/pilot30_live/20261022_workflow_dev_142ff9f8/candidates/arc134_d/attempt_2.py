now = d[mind][0]
ans = [now]
bottom = A[now+N]
ok = 0
for v in sorted(d.keys()):
  for i in d[v]:
    if ans[-1] < i:
      if A[i] < bottom or (A[i] == bottom and ok == 1):
        ans.append(i)
        if ok == 0:
          if A[ans[-1]+N] < A[i+N]:
            ok = 1
          elif A[ans[-1]+N] > A[i+N]:
            ok = -1
