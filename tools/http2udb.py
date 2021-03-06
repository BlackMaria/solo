#!/usr/bin/python
from __future__ import print_function, absolute_import, unicode_literals
from http.server import BaseHTTPRequestHandler,HTTPServer

from fido2.hid import CtapHidDevice, CTAPHID
from fido2.client import Fido2Client, ClientError
from fido2.ctap import CtapError
from fido2.ctap1 import CTAP1
from fido2.ctap2 import *
from fido2.cose import *
from fido2.utils import Timeout, sha256

from intelhex import IntelHex

from ecdsa import SigningKey, NIST256p

import socket,json,base64,ssl,array,binascii

httpport = 8080
udpport = 8111

HEX_FILE = '../efm32/GNU ARM v7.2.1 - Debug/EFM32.hex'

def ForceU2F(client,device):
    client.ctap = CTAP1(device)
    client.pin_protocol = None
    client._do_make_credential = client._ctap1_make_credential
    client._do_get_assertion = client._ctap1_get_assertion


if __name__ == '__main__':
    try:
        dev = next(CtapHidDevice.list_devices(), None)
        print(dev)
        if not dev:
            raise RuntimeError('No FIDO device found')
        client = Fido2Client(dev, 'https://example.com')
        ForceU2F(client, dev)
        ctap = client.ctap
    except Exception as e:
        print(e)


def to_websafe(data):
    data = data.replace('+','-')
    data = data.replace('/','_')
    data = data.replace('=','')
    return data

def from_websafe(data):
    data = data.replace('-','+')
    data = data.replace('_','/')
    return data + '=='[:(3*len(data)) % 4]

def write(data):
    msg = from_websafe(data)
    msg = base64.b64decode(msg)
    chal = b'A'*32
    appid = b'A'*32
    #print (msg)
    #print (msg.decode())
    #print (str(msg))
    #msg = msg.decode('ascii')
    #print('ascii:',repr(msg))
    #print('ascii:',(type(msg)))
    #print(msg + chal)

    #data = client_param + app_param + struct.pack('>B', len(key_handle)) + key_handle
    #msg = str(msg.decode())
    #print(msg.decode())
    s = ctap.authenticate(chal,appid,msg,)
    print(s)
    #sock.sendto(msg, ('127.0.0.1', udpport))

def read():
    #msg = [0]*64
    pkt, _ = sock.recvfrom(1000)
    #for i,v in enumerate(pkt):
        #msg[i] = ord(v)
    msg = base64.b64encode(pkt)
    msg = to_websafe(pkt)
    return msg

def get_firmware_object():
    sk = SigningKey.from_pem(open("signing_key.pem").read())
    h = open(HEX_FILE,'r').read()
    h = base64.b64encode(h.encode())
    h = to_websafe(h.decode())

    num_pages = 64
    START = 0x4000
    END = 2048 * (num_pages - 3) - 4

    ih = IntelHex(HEX_FILE)
    segs = ih.segments()
    arr = ih.tobinarray(start = START, size = END-START)

    im_size = END-START

    print('im_size: ', im_size)
    print('firmware_size: ', len(arr))

    byts = (arr).tobytes() if hasattr(arr,'tobytes') else (arr).tostring()
    sig = sha256(byts)
    print('hash', binascii.hexlify(sig))
    sig = sk.sign_digest(sig)

    print('sig', binascii.hexlify(sig))

    sig = base64.b64encode(sig)
    sig = to_websafe(sig.decode())

    #msg = {'data': read()}
    msg = {'firmware': h, 'signature':sig}
    return msg
class UDPBridge(BaseHTTPRequestHandler):
    def end_headers (self):
        self.send_header('Access-Control-Allow-Origin', '*')
        BaseHTTPRequestHandler.end_headers(self)

    def do_POST(self):
        content_len = int(self.headers.get('Content-Length', 0))
        post_body = self.rfile.read(content_len)
        data = json.loads(post_body)['data']

        print(data)
        msg = from_websafe(data)
        msg = base64.b64decode(msg)
        chal = b"\xf6\xa2\x3c\xa4\x0a\xf9\xda\xd4\x5f\xdc\xba\x7d\xc9\xde\xcb\xed\xb5\x84\x64\x3a\x4c\x9f\x44\xc2\x04\xb0\x17\xd7\xf4\x3e\xe0\x3f"
        appid = b'A'*32

        s = ctap.authenticate(chal,appid,msg,)

        data = struct.pack('B',s.user_presence) + struct.pack('>L',s.counter) + s.signature
        data = base64.b64encode(data).decode('ascii')
        data = to_websafe(data)
        data = json.dumps({'data':data})
        data = data.encode('ascii')

        self.send_response(200)
        self.send_header('Content-type','text/json')
        self.end_headers()
        self.wfile.write(data)


    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type','text/json')

        msg = get_firmware_object()

        self.end_headers()

        self.wfile.write(json.dumps(msg).encode())

try:
    server = HTTPServer(('', httpport), UDPBridge)
    print('Started httpserver on port ' , httpport)

    server.socket = ssl.wrap_socket (server.socket,
            keyfile="../web/localhost.key", 
            certfile='../web/localhost.crt', server_side=True)

    print('Saving signed firmware to firmware.json')
    msg = get_firmware_object()
    wfile = open('firmware.json','wb+')
    wfile.write(json.dumps(msg).encode())
    wfile.close()

    server.serve_forever()

except KeyboardInterrupt:
    server.socket.close()

