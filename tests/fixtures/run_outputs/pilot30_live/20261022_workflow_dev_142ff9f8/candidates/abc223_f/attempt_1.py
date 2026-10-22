from atcoder import lazysegtree
n,q=map(int,input().split())
s=list(input())
st=lazysegtree.LazySegTree(
  lambda x,y:min(x,y),
  n,
  lambda dd,d:dd+d,
  lambda ddd,dd:ddd+dd,
  0,
  [0]*n
)
for i in range(n):
  st.apply(i,i+1,2*(s[i]=="(")-1)
for i in range(q):
  t,l,r=map(int,input().split())
  t-=1
  l-=1
  r-=1
  if t:
    print(["No","Yes"][st.get(l)-1==st.prod(l,r+1)==st.get(r)])
  else:
    st.apply(l,l+1,-2*(s[l]=="(")+1)
    st.apply(r,r+1,-2*(s[r]=="(")+1)
    s[l],s[r]=s[r],s[l]
    st.apply(l,l+1,2*(s[l]=="(")-1)
    st.apply(r,r+1,2*(s[r]=="(")-1)
