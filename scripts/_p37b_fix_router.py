from pathlib import Path
import re

p = Path("backend/app/api/v1/router.py")
t = p.read_text(encoding="utf-8")
# Correct form has exactly one closing paren after the prefix string.
t2, n = re.subn(
    r'router = APIRouter\(prefix="/api/v1"\)\s*\)*',
    'router = APIRouter(prefix="/api/v1")',
    t,
    count=1,
)
p.write_text(t2, encoding="utf-8")
print("replacements", n)
for ln in p.read_text(encoding="utf-8").splitlines():
    if "APIRouter" in ln or ln.strip() == ")":
        print(repr(ln))
