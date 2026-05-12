import os, re

SRC_DIR = 'frontend/src'
PATTERN = re.compile(r'<input\b[^>]*/?>')
LABEL_OPEN = re.compile(r'<label\b')
LABEL_CLOSE = re.compile(r'</label\s*>')
TAG_SCAN = 800

def get_full_tag(content, start):
    scan = content[start:start+TAG_SCAN]
    end = re.search(r'/>', scan)
    if end:
        return scan[:end.end()]
    end2 = re.search(r'(?<!=)>(?!\s*<)', scan)
    if end2:
        return scan[:end2.end()]
    return scan[:200]

def tag_has_label(tag):
    return bool(re.search(r'\baria-label=', tag) or re.search(r'\bid=', tag))

def is_inside_label(content, start):
    preceding = content[:start]
    opens = [m.start() for m in LABEL_OPEN.finditer(preceding)]
    closes = [m.start() for m in LABEL_CLOSE.finditer(preceding)]
    if not opens:
        return False
    last_open = opens[-1]
    if not closes:
        return True
    return last_open > closes[-1]

findings = []
for root, _dirs, files in os.walk(SRC_DIR):
    for filename in files:
        if filename.endswith(('.jsx', '.tsx', '.html')):
            fp = os.path.join(root, filename)
            with open(fp, encoding='utf-8', errors='replace') as fh:
                content = fh.read()
            for match in PATTERN.finditer(content):
                full_tag = get_full_tag(content, match.start())
                if tag_has_label(full_tag):
                    continue
                if is_inside_label(content, match.start()):
                    continue
                lineno = content[:match.start()].count('\n') + 1
                findings.append((fp, lineno, full_tag[:80].replace('\n',' ')))

for fp, ln, snip in findings:
    print(f"{fp}:{ln} | {snip}")
print(f"Total: {len(findings)}")
