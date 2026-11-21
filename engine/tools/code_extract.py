import re
def extract_code(text: str) -> str:
    m = re.search(r"```(?:\w+)?\n(.*?)```", text, re.S)
    return (m.group(1) if m else text).replace("| stopgen |", "").strip()
