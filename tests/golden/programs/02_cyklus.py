sucet = 0
for i in range(3):
    if i % 2 == 0:
        sucet += i
    else:
        sucet -= 1
while sucet < 2:
    sucet += 1
print(sucet)
