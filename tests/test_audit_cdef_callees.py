import unittest
from tools.audit_cdef_callees import examine, psx_image

def synthetic():
    base=0x80010000
    b=bytearray(2048+0x100)
    b[:8]=b'PS-X EXE'
    b[0x18:0x1c]=base.to_bytes(4,'little')
    b[0x1c:0x20]=(0x100).to_bytes(4,'little')
    for i,w in enumerate((0x27bdffe8,0x0c004010,0x8ca20128,0xaca20128,0x03e00008)):
        b[2048+i*4:2052+i*4]=w.to_bytes(4,'little')
    return bytes(b)

class CalleeTests(unittest.TestCase):
    def test_call_target(self):
        r=examine(synthetic(),[0x80010000],0x20)[0]
        self.assertEqual(r['calls_in_window'][0]['target'],'0x80010040')
    def test_memory_load_store(self):
        r=examine(synthetic(),[0x80010000],0x20)[0]
        self.assertEqual([x['kind'] for x in r['memory_ops_in_window']],['load','store'])
    def test_return(self):
        self.assertEqual(examine(synthetic(),[0x80010000],0x20)[0]['jr_ra_locations'],
                         ['0x80010010'])
    def test_bad_header(self):
        with self.assertRaises(ValueError): psx_image(b'bad')
    def test_bad_window(self):
        with self.assertRaises(ValueError): examine(synthetic(),[0x80010000],3)
    def test_out_of_range(self):
        with self.assertRaises(ValueError): examine(synthetic(),[0x80020000],0x20)

if __name__=='__main__': unittest.main()
