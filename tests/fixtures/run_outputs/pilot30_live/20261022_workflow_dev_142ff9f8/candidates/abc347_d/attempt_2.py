a,b,c = map(int, input().split())

cbit = []
popcount = 0
for i in range(60):
    if c & 1<<i != 0:
        cbit.append(1)
        popcount += 1
    else:
        cbit.append(0)

if a+b >= popcount and (a+b)%2 == popcount%2:
    d = (a+b-popcount)//2
    if a-d < 0 or b-d < 0:
        print(-1)
    else:
        ansa = 0
        ansb = 0
        acount = 0
        dcount = 0
        # set bits of c: highest (a-d) go to ansa, rest to ansb
        for i in range(59, -1, -1):
            if cbit[i] == 1:
                if acount < a-d:
                    ansa += 1<<i
                    acount += 1
                else:
                    ansb += 1<<i
        # zero bits of c: lowest d go to both
        for i in range(60):
            if cbit[i] == 0:
                if dcount < d:
                    ansa += 1<<i
                    ansb += 1<<i
                    dcount += 1
        print(ansa,ansb)
else:
    print(-1)
