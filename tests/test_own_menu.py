from pathlib import Path
import hashlib,socket,struct,sys,unittest
from unittest.mock import Mock, patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'lib'))
import native_menu as menu

# Synthetic data with the same lengths and the required navigation bit.
BASELINE = {
 'CarFuncAdap': bytes(60),
 'CarFuncListBap': bytes(range(64)),
 'Coding': bytes(24) + b'\x04',
}
DIGESTS = {name: hashlib.sha256(data).hexdigest() for name, data in BASELINE.items()}


class Session:
 def __init__(self,own=False,other=False):
  self.blocks=dict(BASELINE)
  data=bytearray(BASELINE['CarFuncAdap']);data[menu.OWN_OFFSET]|=int(own);data[menu.CONFIG['preserved_other_menu_offset']]|=int(other)
  self.blocks['CarFuncAdap']=bytes(data);self.sent=[];self.writes=[];self.sock=self;self.ignore=False
 def read_buffer(self,ns,key):return self.blocks[menu.baseline.reads.BY_KEY[(ns,key)][0]]
 def read_int(self,key):
  if key!=menu.OWN_KEY:raise AssertionError('Another package native key was read')
  return self.blocks['CarFuncAdap'][menu.OWN_OFFSET]&31
 def sendall(self,wire):
  key=struct.unpack('>q',wire[-13:-5])[0];value=struct.unpack('>i',wire[-4:])[0]
  if key!=menu.OWN_KEY:raise AssertionError('Another package key was written')
  self.writes.append((key,value))
  if not self.ignore:
   data=bytearray(self.blocks['CarFuncAdap']);data[menu.OWN_OFFSET]=value;self.blocks['CarFuncAdap']=bytes(data)
class OwnMenuTests(unittest.TestCase):
 def setUp(self):
  digests = patch.object(menu, 'BASELINE_DIGESTS', DIGESTS)
  digests.start()
  self.addCleanup(digests.stop)

 def test_codec(self):menu.verify()
 def test_receive_can_wait_after_socket_timeout(self):
  connection = Mock()
  connection.recv.side_effect = socket.timeout
  session = menu.baseline.Session(connection)
  session.receive()
  self.assertEqual(session.events, [])
 def test_all_states_preserve_the_other_package(self):
  for own in (False,True):
   for other in (False,True):
    for enable in (False,True):
     with self.subTest(own=own,other=other,enable=enable):
      session=Session(own,other);before=dict(session.blocks);expected=bytearray(before['CarFuncAdap']);expected[menu.OWN_OFFSET]=int(enable)
      report=menu.change(session,enable,lambda row:None)
      self.assertEqual(report['device_writes'],int(own!=enable));self.assertEqual(session.blocks['CarFuncAdap'],bytes(expected))
      for name in before.keys()-{'CarFuncAdap'}:self.assertEqual(session.blocks[name],before[name])
 def test_idempotent_apply(self):
  session=Session(True,True);menu.change(session,True,lambda row:None);self.assertEqual(session.writes,[])
 def test_other_package_key_is_rejected(self):
  other=216 if menu.OWN_KEY==237 else 237
  with self.assertRaises(ValueError):menu.invoke_int(other,1)
 def test_unknown_configuration_blocks_all_writes(self):
  session=Session();data=bytearray(session.blocks['CarFuncAdap']);data[0]^=1;session.blocks['CarFuncAdap']=bytes(data)
  with self.assertRaises(ValueError):menu.change(session,True,lambda row:None)
  self.assertEqual(session.writes,[])
 def test_uncertain_write_is_not_retried(self):
  session=Session();session.ignore=True
  with self.assertRaises(ValueError):menu.change(session,True,lambda row:None)
  self.assertEqual(session.writes,[(menu.OWN_KEY,1)])
if __name__=='__main__':unittest.main(verbosity=2)
