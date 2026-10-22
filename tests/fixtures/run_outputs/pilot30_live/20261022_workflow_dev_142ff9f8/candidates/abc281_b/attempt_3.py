S = list(input())
if len(S) != 8:
    print("No")
    exit()
if S[0].isdigit() or S[-1].isdigit():
    print("No")
    exit()
if S[1] == "0":
    print("No")
    exit()
for i in range(1, 7):
    if not S[i].isdigit():
        print("No")
        exit()
print("Yes")
