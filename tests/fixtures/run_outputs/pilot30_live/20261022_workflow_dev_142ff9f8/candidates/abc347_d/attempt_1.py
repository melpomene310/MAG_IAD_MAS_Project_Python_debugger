for i in range(59, -1, -1):
    if cbit[i] == 1:
        if acount < a-d:
            ansa += 1<<i
            acount += 1
        else:
            ansb += 1<<i
    else:
        if dcount < d:
            ansa += 1<<i
            ansb += 1<<i
            dcount += 1
