with open('arquivo.txt', 'r') as file:
    for line in file.readlines():
        print(line.strip())
