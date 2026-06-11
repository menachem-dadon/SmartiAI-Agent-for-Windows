file_path = r"smarti/core.py"
with open(file_path, "r", encoding="utf-8") as f:
    content_lines = f.read().splitlines()

start = -1
for i, line in enumerate(content_lines):
    if "def _schedule_background_task_thread" in line:
        start = i
        break

if start != -1:
    for idx in range(start, start + 75):
        print(f"{idx}: {repr(content_lines[idx])}")
