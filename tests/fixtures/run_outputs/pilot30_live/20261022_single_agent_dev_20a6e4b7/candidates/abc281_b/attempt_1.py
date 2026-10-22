S = list(input().strip())
if len(S) != 8:
    print("No")
    exit()
elif not S[0].isdigit() and not S[-1].isdigit() and S[1] != "0":
    for i in range(6):
        if not S[i + 1].isdigit():
            print("No")
            exit()
else:
    print("No")
    exit()
print("Yes")
