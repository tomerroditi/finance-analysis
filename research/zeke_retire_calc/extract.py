"""Extract the Chart.js series embedded in a zekestories result HTML blob."""
import re, json


def charts(h):
    """Return {canvas_id: {'labels': [...], 'datasets': [{'label':..,'data':[..]}]}}."""
    out = {}
    for m in re.finditer(r'<canvas id="([^"]+)"></canvas>\s*<script>(.*?)</script>', h, re.S):
        cid, body = m.group(1), m.group(2)
        labels = _arr(body, r'labels:\s*\[')
        ds = []
        for dm in re.finditer(r'\{([^{}]*?)data:\s*\[([^\]]*)\]([^{}]*)\}', body, re.S):
            blob = dm.group(1) + dm.group(3)
            lab = re.search(r'label:\s*[\'"](.*?)[\'"]', blob)
            data = _nums(dm.group(2))
            if data:
                ds.append({"label": lab.group(1) if lab else None, "n": len(data), "data": data})
        typ = re.search(r'type:\s*[\'"](\w+)[\'"]', body)
        out.setdefault(cid, {"type": typ.group(1) if typ else None,
                             "labels": labels, "datasets": ds})
    return out


def _arr(body, pat):
    m = re.search(pat, body)
    if not m:
        return []
    i = m.end()
    depth = 1
    j = i
    while j < len(body) and depth:
        if body[j] == '[':
            depth += 1
        elif body[j] == ']':
            depth -= 1
        j += 1
    return _nums(body[i:j - 1])


def _nums(s):
    vals = []
    for tok in s.split(','):
        tok = tok.strip().strip("'\"")
        if not tok:
            continue
        try:
            vals.append(float(tok))
        except ValueError:
            vals.append(tok)
    return vals
