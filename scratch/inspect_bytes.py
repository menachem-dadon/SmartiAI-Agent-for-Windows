with open("smarti/core.py", "rb") as f:
    lines = f.readlines()

for idx in range(3600, 3608):
    if idx < len(lines):
        print(f"{idx}: {lines[idx]}")
