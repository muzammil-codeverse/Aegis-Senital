import re

fp = 'frontend/src/components/analytics/AnalyticsFilterBar.jsx'
with open(fp, encoding='utf-8') as f:
    content = f.read()

# Find the input at line 37
pattern = re.compile(r'<input\b(?![^>]*\baria-label=)(?![^>]*\bid=)[^>]*/?>')
for m in pattern.finditer(content):
    lineno = content[:m.start()].count('\n') + 1
    if lineno in (37, 53):
        window = content[max(0, m.start()-600):m.start()]
        opens = len(re.findall(r'<label\b', window))
        closes = len(re.findall(r'</label\s*>', window))
        print(f"line {lineno}: opens={opens}, closes={closes}, inside_label={opens>closes}")
        print(f"  window tail: ...{window[-200:]!r}")
