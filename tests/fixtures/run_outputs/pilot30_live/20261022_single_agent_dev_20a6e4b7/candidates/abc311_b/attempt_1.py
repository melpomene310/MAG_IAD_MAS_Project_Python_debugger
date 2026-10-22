
def check(b,c):
  for i in range(N):
    for j in range(b,c+1):
      if(a[i][j] == 'x'):
        return False
  return True

a = []
N,D = map(int,input().split())

for i in range(N):
  s = input()
  a.append(s)
ans = 0
for i in range(D):
  for j in range(i,D):
    if(check(i,j) == True):
      ans = max(ans,j-i+1)

print(ans)
