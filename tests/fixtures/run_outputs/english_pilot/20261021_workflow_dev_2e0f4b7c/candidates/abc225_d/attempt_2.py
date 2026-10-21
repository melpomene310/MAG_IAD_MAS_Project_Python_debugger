N,Q=map(int,input().split())
connects=[[-1,-1] for _ in range(N)]
head=list(range(N))
tail=list(range(N))

for _ in range(Q):
    query=list(map(int,input().split()))
    t=query[0]
    x=query[1]-1
    if t==1:
        y=query[2]-1
        connects[x][1]=y
        connects[y][0]=x
        head[y]=head[x]
        tail[head[x]]=y
    elif t==2:
        y=query[2]-1
        connects[x][1]=-1
        connects[y][0]=-1
        head[y]=y
        tail[x]=x
    else:
        h=head[x]
        t2=tail[h]
        print(t2-h+1,h+1,t2+1)
