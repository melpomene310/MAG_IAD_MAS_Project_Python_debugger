BigPrime = 998244353

N = int(input())

def modinv(a, b):
    return pow(a, b-2, b)

def mod_time(a,b):
    return (a*b) % BigPrime

n = modinv(N, BigPrime)
M = (N ** 2) % BigPrime
m = modinv(M, BigPrime)
fraci = [0] * (N+1)
complementfraci = [0] * (N+1)
poweri = [0] * (N+1)
rate2jou = [0] * (N+1)
for i in range(1, N+1):
    fraci[i] = (fraci[i-1] + n) % BigPrime
    complementfraci[i] = (BigPrime - fraci[i]+1) % BigPrime
for i in range(1, N+1):
    poweri[i] = (i**2) % BigPrime
    rate2jou[i] = mod_time(poweri[i], m)

# Precompute inverses of (BigPrime+1 - rate2jou[i]) for all i
inv_rate = [0] * (N+1)
for i in range(N+1):
    inv_rate[i] = modinv(BigPrime+1 - rate2jou[i], BigPrime)

def limitPr(init, i):
    init = init % BigPrime
    return mod_time(init, inv_rate[i])

def first_to_second(i):
    return limitPr(complementfraci[i], i)

def val_first(i):
    return limitPr(fraci[i], i)

ans = [0, 0]
Prob = [[0, 0] for _ in range(N+1)]
Prob[0] = [1, 0]

for i in range(N):
    f_s = first_to_second(i)
    f_f = mod_time(f_s, fraci[i])
    Prob[i+1][0] = (mod_time(f_f, Prob[i][0]) + mod_time(f_s, Prob[i][1])) % BigPrime
    Prob[i+1][1] = (BigPrime - Prob[i+1][0]+1) % BigPrime
    v_f = val_first(i)
    v_s = mod_time(v_f, fraci[i])

    ans[0] = (ans[0] + (mod_time(v_f, Prob[i][0]) + mod_time(v_s, Prob[i][1]))) % BigPrime
    ans[1] = (ans[1] + (mod_time(v_s, Prob[i][0]) + mod_time(v_f, Prob[i][1]))) % BigPrime

print(*ans)
