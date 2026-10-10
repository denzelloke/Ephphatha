"""Usage: python3 export_model_header.py path/to/model.tflite
Writes model.h alongside this script. Does not change shape/type/normalization.
"""
from pathlib import Path
import sys
if len(sys.argv) != 2:
    raise SystemExit('Usage: python3 export_model_header.py path/to/model.tflite')
raw = Path(sys.argv[1]).read_bytes()
if len(raw) < 8 or raw[4:8] != b'TFL3':
    raise SystemExit('Not a TFL3 model file')
rows = [', '.join(f'0x{x:02x}' for x in raw[i:i+12]) for i in range(0,len(raw),12)]
out = Path(__file__).resolve().parent / 'model.h'
out.write_text('#pragma once\nalignas(16) const unsigned char g_model[] = {\n  '+',\n  '.join(rows)+'\n};\nconst unsigned int g_model_len = sizeof(g_model);\n')
print(f'Wrote {out} ({len(raw)} model bytes)')
