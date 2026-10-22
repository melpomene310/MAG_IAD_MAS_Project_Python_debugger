K = int(input())

if K > 69:
    print(f"22:{K - 60}")
elif K > 59:
    print(f"22:0{K - 60}")
else:
    print(f"21:{K:02d}")
