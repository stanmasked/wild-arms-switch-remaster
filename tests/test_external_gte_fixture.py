import unittest
from tools.compare_gte_rtps_vectors import FIELDS, compare

class FixtureContract(unittest.TestCase):
    def setUp(self):
        self.vector={'source':'hardware','input':[0]*22,
                     'expected':{'sz3':50,'flag':0}}
        self.output=dict.fromkeys(FIELDS,0)
        self.output['sz3']=50

    def test_matching_values(self):
        self.assertEqual(compare(self.vector,self.output),{})

    def test_mismatch_reports_register(self):
        self.output['sz3']=49
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

if __name__=='__main__':
    unittest.main()
