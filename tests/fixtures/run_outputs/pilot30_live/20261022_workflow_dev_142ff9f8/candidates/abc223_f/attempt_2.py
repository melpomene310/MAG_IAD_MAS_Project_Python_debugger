from atcoder import lazysegtree
n,q=map(int,input().split())
s=list(input())
p=[0]*(n+1)
for i in range(n):
    p[i+1]=p[i]+(2*(s[i]=="(")-1)
st=lazysegtree.LazySegTree(
  lambda x,y:min(x,y),
  n+1,
  lambda dd,d:dd+d,
  lambda ddd,dd:ddd+dd,
  0,
  p
)
for i in range(q):
  t,l,r=map(int,input().split())
  t-=1
  l-=1
  r-=1
  if t:
    print(["No","Yes"][st.get(l)==st.prod(l,r+2)==st.get(r+1)])
  else:
    old_l=2*(s[l]=="(")-1
    old_r=2*(s[r]=="(")-1
    s[l],s[r]=s[r],s[l]
    new_l=2*(s[l]=="(")-1
    new_r=2*(s[r]=="(")-1
    st.apply(l+1,n+1,new_l-old_l)
    st.apply(r+1,n+1,new_r-old_r)
