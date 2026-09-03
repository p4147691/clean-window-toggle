from pathlib import Path

manifest = Path('manifest.json')
text = manifest.read_text(encoding='utf-8')
old = '"version": "2.3.9"'
new = '"version": "2.3.10"'
assert old in text, 'manifest version not found'
manifest.write_text(text.replace(old, new, 1), encoding='utf-8')

runtime = Path('windowed_fullscreen.js')
text = runtime.read_text(encoding='utf-8')
old = 'const RUNTIME_VERSION = "2.3.9";'
new = 'const RUNTIME_VERSION = "2.3.10";'
assert old in text, 'runtime version not found'
runtime.write_text(text.replace(old, new, 1), encoding='utf-8')
