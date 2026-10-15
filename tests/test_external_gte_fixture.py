import unittest
from tools.compare_gte_rtps_vectors import FIELDS, compare, validate

class FixtureContract(unittest.TestCase):
    def setUp(self):
        self.vector = {'source':'hardware','input':[0]*22,
                       'expected':{'sz3':50,'flag':0}}
        self.output = dict.fromkeys(FIELDS,0)
        self.output['sz3'] = 50

    def test_matching_values(self):
        self.assertEqual(compare(self.vector,self.output),{})

    def test_mismatch_reports_register(self):
        self.output['sz3'] = 49
        self.assertEqual(compare(self.vector,self.output)['sz3'],
                         {'expected':50,'actual':49})

    def test_rejects_self_generated_reference(self):
        self.vector['source']='host_reference'
        with self.assertRaises(ValueError):compare(self.vector,self.output)

    def test_rejects_empty_expectations(self):
        self.vector['expected']={}
        with self.assertRaises(ValueError):compare(self.vector,self.output)

    def test_rejects_wrong_input_count(self):
        self.vector['input']=[0]*21
        with self.assertRaises(ValueError):compare(self.vector,self.output)

    def test_rejects_matrix_overflow(self):
        self.vector['input'][0]=32768
        with self.assertRaises(ValueError):validate(self.vector)

    def test_rejects_negative_projection_h(self):
        self.vector['input'][15]=-1
        with self.assertRaises(ValueError):validate(self.vector)

    def test_rejects_invalid_sf_and_boolean(self):
        self.vector['input'][20]=2
        with self.assertRaises(ValueError):validate(self.vector)
        self.vector['input'][20]=True
        with self.assertRaises(ValueError):validate(self.vector)

    def test_rejects_expected_flag_overflow(self):
        self.vector['expected']['flag']=0x100000000
        with self.assertRaises(ValueError):validate(self.vector)

    def test_rejects_expected_boolean(self):
        self.vector['expected']['sz3']=False
        with self.assertRaises(ValueError):validate(self.vector)

    def test_rejects_unrecognized_output(self):
        self.vector['expected']['not_a_register']=0
        with self.assertRaises(ValueError):validate(self.vector)

    def test_accepts_boundary_values(self):
        inp=self.vector['input']
        inp[0]=-32768;inp[9]=-2147483648;inp[15]=65535
        inp[16]=2147483647;inp[18]=32767;inp[19]=-2147483648
        inp[20]=1;inp[21]=0
        self.vector['expected']={'sxy2':4294967295,'flag':0xffffffff,
                                 'ir3':-32768,'mac3':2147483647}
        self.assertEqual(validate(self.vector),self.vector['expected'])

    def test_rejects_missing_output(self):
        self.output.pop('sz3')
        with self.assertRaises(ValueError):compare(self.vector,self.output)

if __name__=='__main__':
    unittest.main()
