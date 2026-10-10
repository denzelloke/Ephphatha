"""Build a tiny float32 identity Dense TFLite model using only Python stdlib.
No training: four voltage inputs become four class scores through W=I, b=0.
This minimal forward FlatBuffer writer emits schema version 3, FC op version 1.
"""
from pathlib import Path
import struct

class Builder:
    def __init__(self): self.data = bytearray(b'\0\0\0\0TFL3')
    def align(self, n=4):
        while len(self.data) % n: self.data.append(0)
    def u32(self, pos, value): struct.pack_into('<I', self.data, pos, value)
    def ref(self, pos, target):
        assert target > pos
        self.u32(pos, target-pos)
    def table(self, fields):
        self.align(2)
        vt = len(self.data)
        n = len(fields)
        self.data += struct.pack('<HH', 4+2*n, 4+4*n)
        for i in range(n): self.data += struct.pack('<H', 0 if fields[i] == 'omit' else 4+4*i)
        self.align()
        obj = len(self.data)
        self.data += struct.pack('<i', obj-vt) + b'\0'*(4*n)
        for i, value in enumerate(fields):
            if value is not None and value != 'omit': self.u32(obj+4+4*i, value)
        return obj, [obj+4+4*i for i in range(n)]
    def vec(self, values):
        self.align()
        p=len(self.data)
        self.data += struct.pack('<I',len(values))
        for v in values: self.data += struct.pack('<i',v)
        return p
    def refs(self, count):
        p=self.vec([0]*count)
        return p,[p+4+4*i for i in range(count)]
    def string(self, text):
        self.align(); p=len(self.data); raw=text.encode()
        self.data += struct.pack('<I',len(raw))+raw+b'\0'
        return p
    def floats(self, values):
        self.align(16)
        # Align vector DATA, rather than its length, to 16 bytes.
        self.data += b'\0'*12
        p=len(self.data)
        self.data += struct.pack('<I',4*len(values))
        self.data += struct.pack('<'+'f'*len(values),*values)
        return p

b=Builder()
m,mf=b.table([3,None,None,None,None]); b.u32(0,m)
v,slots=b.refs(1); b.ref(mf[1],v)
opcode,_=b.table([9,'omit',1,9]); b.ref(slots[0],opcode)
v,slots=b.refs(1); b.ref(mf[2],v)
g,gf=b.table([None,None,None,None,None]); b.ref(slots[0],g)
v,slots=b.refs(4); b.ref(gf[0],v)
for slot,shape,buffer,name in zip(slots,[[1,4],[4,4],[4],[1,4]],[0,1,2,0],['voltages','weights','bias','scores']):
    t,tf=b.table([None,0,buffer,None]); b.ref(slot,t)
    b.ref(tf[0],b.vec(shape)); b.ref(tf[3],b.string(name))
b.ref(gf[1],b.vec([0])); b.ref(gf[2],b.vec([3]))
v,slots=b.refs(1); b.ref(gf[3],v)
op,of=b.table([0,None,None,8,None]); b.ref(slots[0],op)
b.ref(of[1],b.vec([0,1,2])); b.ref(of[2],b.vec([3]))
opts,_=b.table([0,0,0]); b.ref(of[4],opts)
b.ref(gf[4],b.string('four_voltage_dummy'))
b.ref(mf[3],b.string('Dummy identity dense classifier; NOT trained sign recognition'))
v,slots=b.refs(3); b.ref(mf[4],v)
empty,_=b.table([]); b.ref(slots[0],empty)
for slot,values in zip(slots[1:],[[float(i==j) for i in range(4) for j in range(4)],[0.0]*4]):
    buf,bf=b.table([None]); b.ref(slot,buf); b.ref(bf[0],b.floats(values))
root=Path(__file__).resolve().parent
raw=bytes(b.data)
(root/'dummy_model.tflite').write_bytes(raw)
rows=[', '.join(f'0x{x:02x}' for x in raw[i:i+12]) for i in range(0,len(raw),12)]
(root/'model.h').write_text('#pragma once\n// Generated dummy TFLite model: Dense(4), identity weights, zero bias.\nalignas(16) const unsigned char g_model[] = {\n  '+',\n  '.join(rows)+'\n};\nconst unsigned int g_model_len = sizeof(g_model);\n')
print(f'Generated {len(raw)}-byte model and model.h')
