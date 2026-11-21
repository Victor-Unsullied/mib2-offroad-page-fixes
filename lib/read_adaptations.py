"""Codec for the three Offroad configuration buffer reads."""
import hashlib
import re
import struct

MAGIC=b'\x03\x04\x05\x01'
SERVICE='org.dsi.ifc.persistence.DSIPersistence'
READS = (
    ('CarFuncAdap', 28442848, 101, 60),
    ('CarFuncListBap', 28442848, 103, 64),
    ('Coding', 28180695, 1, 25),
)
BY_KEY={(ns,key):(name,length) for name,ns,key,length in READS}
ERRORS={0:'NO_ERRORS',1:'INVALID_NAMESPACE',2:'INVALID_KEY',3:'NOSPACE',4:'TRANSACTION_FAILED',
        5:'CORRUPT_DATA',6:'NO_DEVICE_AVAILABLE',7:'WRONG_PARAMETER_LENGTH',8:'STATUS_TIME_OUT',
        9:'DEVICE_BUSY',10:'DUMMY_DATA',11:'NOT_NOTIFIED',12:'INVALID_TIMEOUT',13:'ALREADY_PENDING',
        14:'NOT_SUBSCRIBED',15:'OVERLOAD'}

def string(value):
    encoded=value.encode('utf-16-be')
    return struct.pack('>i',len(encoded)//2)+encoded

def envelope(channel,payload):
    if channel not in (100,102):raise ValueError('Non-whitelisted channel')
    body=bytes(5)+bytes((255,channel))+payload
    return MAGIC+struct.pack('<II8sHH',0,0x04000000,bytes(8),1,len(body))+body

def read_payload(namespace,key):
    if (namespace,key) not in BY_KEY:raise ValueError('Only the three fixed read keys are allowed')
    return (b'\0'+string(SERVICE)+struct.pack('>i',0)+string('readBuffer')+struct.pack('>i',2)
            +b'\0'+struct.pack('>i',namespace)+b'\1'+struct.pack('>q',key))

def read_request(namespace,key):return envelope(102,read_payload(namespace,key))
def registration_request():return envelope(100,struct.pack('>i',13))

class Frames:
    def __init__(self):self.buffer=bytearray()
    def feed(self,data):
        self.buffer.extend(data)
        while len(self.buffer)>=24:
            if self.buffer[:3]!=MAGIC[:3]:raise ValueError('Unexpected DebugSPI framing')
            kind,length=struct.unpack_from('<HH',self.buffer,20)
            if len(self.buffer)<24+length:return
            body=bytes(self.buffer[24:24+length]);del self.buffer[:24+length]
            yield kind,body

class Reader:
    def __init__(self,data,position=0):self.data=data;self.position=position
    def take(self,length):
        if length<0 or self.position+length>len(self.data):raise ValueError('Truncated response')
        value=self.data[self.position:self.position+length];self.position+=length;return value
    def number(self,fmt):return struct.unpack(fmt,self.take(struct.calcsize(fmt)))[0]
    def tag(self,expected):
        if self.number('>B')!=expected:raise ValueError('Unexpected DSI argument type')
    def text(self):
        length=self.number('>i')
        if not 0<=length<=8192:raise ValueError('Unexpected response string length')
        return self.take(length*2).decode('utf-16-be')
    def finished(self):
        if self.position!=len(self.data):raise ValueError('Trailing response bytes')

def invocation_ack(kind,body):
    if kind!=102 or len(body)<7 or body[5]!=10:return None
    reader=Reader(body,6);success=reader.number('>B')
    if success not in (0,1):raise ValueError('Malformed invocation acknowledgement')
    error=None if success else reader.text();reader.finished()
    return {'dispatch_success':bool(success),'error':error,
            'meaning':'Dispatch acknowledgement only; not persistence result or data'}

def primitive_bytes(text):
    if not text.startswith('byte[') or not text.endswith(']'):raise ValueError('Expected native byte[] representation')
    middle=text[5:-1]
    if not middle:return b''
    tokens=middle.split(', ')
    if len(tokens)>4096:raise ValueError('Oversized persistence buffer')
    values=[]
    for token in tokens:
        if not re.fullmatch(r'0|[1-9][0-9]*|-[1-9][0-9]*',token):raise ValueError('Noncanonical byte array')
        value=int(token)
        if not -128<=value<=127:raise ValueError('Byte outside signed native range')
        values.append(value&255)
    return bytes(values)

def decode_buffer(kind,body):
    if kind!=272 or len(body)<51 or body[5:7]!=b'\xf9\x05':return None
    trace_target,service,instance,method,argc=struct.unpack_from('>iiiii',body,31)
    if (service,instance,method)!=(105,0,16):return None
    if argc!=4:raise ValueError('Unexpected Persistence.readBuffer response arity')
    reader=Reader(body,51)
    reader.tag(1);namespace=reader.number('>i')
    reader.tag(8);key=reader.number('>q')
    # Do not interpret another feature's persistence data.
    if (namespace,key) not in BY_KEY:return None
    tag=reader.number('>B')
    if tag==0:raw=None;representation=None
    elif tag==10:
        representation=reader.text();raw=primitive_bytes(representation)
    else:raise ValueError('Expected null or primitive byte[] response')
    reader.tag(1);result=reader.number('>i');reader.finished()
    name,expected=BY_KEY[(namespace,key)]
    record={'name':name,'namespace':namespace,'namespace_hex':hex(namespace),'key':key,
            'trace_target':trace_target,'result':result,'result_name':ERRORS.get(result,'UNKNOWN'),
            'raw_representation':representation,'raw_hex':None if raw is None else raw.hex(),
            'raw_length':None if raw is None else len(raw),'expected_length':expected,
            'raw_sha256':None if raw is None else hashlib.sha256(raw).hexdigest(),
            'usable':result==0 and raw is not None and len(raw)==expected}
    return record
