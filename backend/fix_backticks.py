import re
with open('app.py', 'r') as f:
    content = f.read()

# Replace backtick-based dict syntax: {`key`: `value`} -> {'key': 'value'}
content = re.sub(r'\{`([^`]*)`:\s*`([^`]*)`\}', lambda m: "{'" + m.group(1) + "': '" + m.group(2) + "'}", content)

# Also fix standalone backtick strings used as values: `value` -> 'value'
# Pattern: : `some text`
content = re.sub(r':\s*`([^`]*)`', lambda m: ": '" + m.group(1) + "'", content)

with open('app.py', 'w') as f:
    f.write(content)
print('Fixed backtick syntax')
