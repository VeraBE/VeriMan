import os
import shutil
from unittest import TestCase
from veriman import VeriMan
from tools import read_config


class TestVeriMan(TestCase):

    @classmethod
    def setUpClass(cls):
        cls.veriman = VeriMan()
        cls.inorder_config = TestVeriMan.read_test_config()
        cls.inorder_config.contract.path = os.path.dirname(os.path.abspath(__file__)) + '/InOrder.sol'


    @classmethod
    def tearDownClass(cls):
        path_to_remove = os.path.dirname(os.path.abspath(__file__)) + '/output'
        if os.path.isdir(path_to_remove):
            shutil.rmtree(path_to_remove)


    @staticmethod
    def read_test_config():
        test_config = read_config('config_tests.json')
        user_config = read_config('../config.json')
        test_config.verification.verisol.path = user_config.verification.verisol.path
        return test_config


    def check_error_output(self, proof_found, actual_verisol_counterexample, expected_verisol_counterexample):
        self.assertFalse(proof_found)
        self.assertEqual(actual_verisol_counterexample, expected_verisol_counterexample)


    def check_no_error_output(self, verisol_counterexample):
        self.assertEqual(len(verisol_counterexample), 0)


    def test_integer_comparison_false(self):
        self.inorder_config.instrumentation.predicates = ['num_calls > 0']
        proof_found, verisol_counterexample = self.veriman.analyze_contract(self.inorder_config)
        self.check_error_output(proof_found, verisol_counterexample, ['a', 'b', 'b'])


    def test_integer_comparison_true(self):
        self.inorder_config.instrumentation.predicates = ['num_calls >= 0']
        proof_found, verisol_counterexample = self.veriman.analyze_contract(self.inorder_config)
        self.assertFalse(proof_found)
        self.check_no_error_output(verisol_counterexample)


    def test_implies_false(self):
        self.inorder_config.instrumentation.predicates = ['a_called -> b_called']
        proof_found, verisol_counterexample = self.veriman.analyze_contract(self.inorder_config)
        self.check_error_output(proof_found, verisol_counterexample, ['a'])


    def test_implies_true(self):
        self.inorder_config.instrumentation.predicates = ['b_called -> a_called']
        proof_found, verisol_counterexample = self.veriman.analyze_contract(self.inorder_config)
        self.assertTrue(proof_found)
        self.check_no_error_output(verisol_counterexample)


    def test_previously_false(self):
        self.inorder_config.instrumentation.predicates = ['previously(!a_called) && a_called']
        proof_found, verisol_counterexample = self.veriman.analyze_contract(self.inorder_config)
        self.check_error_output(proof_found, verisol_counterexample, ['a', 'a'])


    def test_previously_true(self):
        self.inorder_config.instrumentation.predicates = ['previously(num_calls >= 0) && (num_calls >= 0)']
        proof_found, verisol_counterexample = self.veriman.analyze_contract(self.inorder_config)
        self.assertFalse(proof_found)
        self.check_no_error_output(verisol_counterexample)


    def test_since_false(self):
        self.inorder_config.instrumentation.predicates = ['since(num_calls > 0, a_called)']
        proof_found, verisol_counterexample = self.veriman.analyze_contract(self.inorder_config)
        self.check_error_output(proof_found, verisol_counterexample, ['a', 'b', 'b'])


    def test_since_true(self):
        self.inorder_config.instrumentation.predicates = ['since(num_calls >= 0, a_called)']
        proof_found, verisol_counterexample = self.veriman.analyze_contract(self.inorder_config)
        self.assertFalse(proof_found)
        self.check_no_error_output(verisol_counterexample)


    def test_once_false(self):
        self.inorder_config.instrumentation.predicates = ['once(num_calls == 2)']
        proof_found, verisol_counterexample = self.veriman.analyze_contract(self.inorder_config)
        self.check_error_output(proof_found, verisol_counterexample, ['a'])


    def test_once_true(self):
        self.inorder_config.instrumentation.predicates = ['a_called -> once(num_calls > 0)']
        proof_found, verisol_counterexample = self.veriman.analyze_contract(self.inorder_config)
        self.assertFalse(proof_found)
        self.check_no_error_output(verisol_counterexample)


    def test_always_false(self):
        self.inorder_config.instrumentation.predicates = ['always(num_calls < 3)']
        proof_found, verisol_counterexample = self.veriman.analyze_contract(self.inorder_config)
        self.check_error_output(proof_found, verisol_counterexample, ['a', 'a', 'a'])


    def test_always_true(self):
        self.inorder_config.instrumentation.predicates = ['always(num_calls >= 0)']
        proof_found, verisol_counterexample = self.veriman.analyze_contract(self.inorder_config)
        self.assertFalse(proof_found)
        self.check_no_error_output(verisol_counterexample)


    def test_parameters(self):
        params_config = TestVeriMan.read_test_config()
        params_config.contract.path = os.path.dirname(os.path.abspath(__file__)) + '/InOrderWithParams.sol'
        params_config.instrumentation.instrument = False

        proof_found, verisol_counterexample = self.veriman.analyze_contract(params_config)

        self.check_error_output(proof_found, ['a', 'b', 'c'], verisol_counterexample)


    def test_instrumentation_only(self):
        contract_name = 'PaymentSplitter'
        instrumentation_only_config = TestVeriMan.read_test_config()
        instrumentation_only_config.contract.path = os.path.dirname(os.path.abspath(__file__)) + '/' + contract_name + '.sol'
        instrumentation_only_config.instrumentation.predicates = ['_totalReleased <= _totalShares']
        instrumentation_only_config.verification.verify = False

        proof_found, verisol_counterexample = self.veriman.analyze_contract(instrumentation_only_config)

        self.assertFalse(proof_found)
        self.check_no_error_output(verisol_counterexample) # FIXME

        instrumented_file_name = contract_name + '_toAnalyze_merged.sol'

        self.assertTrue(os.path.isfile(instrumented_file_name))

        # TODO check more

        os.remove(instrumented_file_name)