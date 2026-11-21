"""Read only the Offroad menu scalar and its configuration buffers."""
import socket
import struct
import time

import read_adaptations as reads

NS = 27263191
KEYS = {216: 'offroad'}

def invoke_int(key,value=None):
    if key not in KEYS:raise ValueError('Unreviewed key')
    if value is not None:raise ValueError('Read-only invocation')
    args=b'\0'+struct.pack('>i',NS)+b'\1'+struct.pack('>q',key)
    return reads.envelope(102,b'\0'+reads.string(reads.SERVICE)+struct.pack('>i',0)+reads.string('readInt')+struct.pack('>i',2)+args)
def int_response(kind,body):
    if kind!=272 or len(body)<51 or body[5:7]!=b'\xf9\x05':return None
    target,service,instance,method,argc=struct.unpack_from('>iiiii',body,31)
    if (service,instance,method)!=(105,0,9):return None
    r=reads.Reader(body,51);r.tag(1);ns=r.number('>i');r.tag(8);key=r.number('>q')
    if ns!=NS or key not in KEYS:return None
    if argc!=4:raise ValueError('Unexpected integer arity')
    r.tag(1);value=r.number('>i');r.tag(1);result=r.number('>i');r.finished()
    return {'kind':'readInt','namespace':ns,'key':key,'name':KEYS[key],'value':value,'result':result}
class Session:
    def __init__(self,sock):self.sock=sock;self.parser=reads.Frames();self.raw=bytearray();self.events=[];self.sent=[]
    def receive(self):
        try:part=self.sock.recv(65536)
        except socket.timeout:return
        if not part:raise ConnectionError('Debug stream closed')
        self.raw.extend(part)
        if len(self.raw)>20000000:raise ValueError('Capture limit')
        for kind,body in self.parser.feed(part):
            for decoder in (reads.invocation_ack,reads.decode_buffer,int_response):
                event=decoder(kind,body)
                if event is not None:self.events.append(event)
    def request(self,wire,label,predicate):
        offset=len(self.events);self.sock.sendall(wire);self.sent.append({'label':label,'hex':wire.hex()})
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            self.receive()
            for event in self.events[offset:]:
                if event.get('dispatch_success') is False:raise ValueError('Invocation rejected')
                if predicate(event):return event
        raise TimeoutError(label+' result missing')
    def read_int(self,key):
        event=self.request(invoke_int(key),'readInt '+str(key),lambda e:e.get('kind')=='readInt' and e.get('key')==key)
        if event['result']!=0 or not 0<=event['value']<=255:raise ValueError('Invalid native integer '+str(event))
        return event['value']
    def read_buffer(self,ns,key):
        event=self.request(reads.read_request(ns,key),'readBuffer '+str(ns)+'/'+str(key),lambda e:e.get('namespace')==ns and e.get('key')==key and 'raw_hex' in e)
        if event['result']!=0 or event['raw_length']!=reads.BY_KEY[(ns,key)][1]:raise ValueError('Invalid native buffer')
        return bytes.fromhex(event['raw_hex'])
