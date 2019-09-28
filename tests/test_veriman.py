import os
import shutil
import subprocess
from unittest import TestCase
from veriman import VeriMan


# TODO move to constants file?
INSTRUMENTED_FILE_END = '_VERIMAN.sol'


class TestVeriMan(TestCase):

    @classmethod
    def setUpClass(cls):
        cls.veriman = VeriMan()
        cls.inorder_config = TestVeriMan.get_test_config()
        cls.inorder_config.contract.path = os.path.dirname(os.path.abspath(__file__)) + '/InOrder.sol'


    @classmethod
    def tearDownClass(cls):
        path_to_remove = os.path.dirname(os.path.abspath(__file__)) + '/output'
        if os.path.isdir(path_to_remove):
            shutil.rmtree(path_to_remove)


    @staticmethod
    def get_test_config():
        test_config = VeriMan.parse_config('config_tests.json')
        user_config = VeriMan.parse_config('../config.json')
        test_config.verification.verisol.path = user_config.verification.verisol.path
        return test_config


    def check_error_output(self, proof_found, actual_verisol_counterexample, expected_verisol_counterexample):
        self.assertFalse(proof_found)
        self.assertEqual(actual_verisol_counterexample, expected_verisol_counterexample)


    def check_no_error_output(self, verisol_counterexample):
        self.assertEqual(len(verisol_counterexample), 0)


    def check_contract_compiles(self, file_name):
        solc_process = subprocess.Popen(['solc ' + file_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        solc_process.wait()
        solc_process.stdout.close()
        solc_process.stderr.close()
        self.assertEqual(solc_process.returncode, 0)


    def test_integer_comparison_false(self):
        self.inorder_config.instrumentation.predicates = ['num_calls > 0']
        proof_found, verisol_counterexample = self.veriman.analyze_contract(self.inorder_config)
        self.check_error_output(proof_found, verisol_counterexample, ['Constructor'])


    def test_integer_comparison_true(self):
        self.inorder_config.instrumentation.predicates = ['num_calls >= 0']
        proof_found, verisol_counterexample = self.veriman.analyze_contract(self.inorder_config)
        self.assertFalse(proof_found)
        self.check_no_error_output(verisol_counterexample)


    def test_implies_false(self):
        self.inorder_config.instrumentation.predicates = ['a_called -> num_calls > 0']
        proof_found, verisol_counterexample = self.veriman.analyze_contract(self.inorder_config)
        self.check_error_output(proof_found, verisol_counterexample, ['Constructor', 'a', 'b', 'b'])


    def test_implies_true(self):
        self.inorder_config.instrumentation.predicates = ['b_called -> a_called']
        proof_found, verisol_counterexample = self.veriman.analyze_contract(self.inorder_config)
        self.assertTrue(proof_found)
        self.check_no_error_output(verisol_counterexample)


    def test_previously_false(self):
        self.inorder_config.instrumentation.predicates = ['previously(!a_called) && a_called']
        proof_found, verisol_counterexample = self.veriman.analyze_contract(self.inorder_config)
        self.check_error_output(proof_found, verisol_counterexample, ['Constructor'])


    def test_previously_true(self):
        self.inorder_config.instrumentation.predicates = ['previously(num_calls >= 0) && (num_calls >= 0)']
        proof_found, verisol_counterexample = self.veriman.analyze_contract(self.inorder_config)
        self.assertFalse(proof_found)
        self.check_no_error_output(verisol_counterexample)


    def test_since_false(self):
        self.inorder_config.instrumentation.predicates = ['since(num_calls > 0, a_called)']
        proof_found, verisol_counterexample = self.veriman.analyze_contract(self.inorder_config)
        self.check_error_output(proof_found, verisol_counterexample, ['Constructor'])


    def test_since_true(self):
        self.inorder_config.instrumentation.predicates = ['c_called -> since(num_calls >= 0, a_called)']
        proof_found, verisol_counterexample = self.veriman.analyze_contract(self.inorder_config)
        self.assertFalse(proof_found)
        self.check_no_error_output(verisol_counterexample)


    def test_once_false(self):
        self.inorder_config.instrumentation.predicates = ['once(num_calls == 2)']
        proof_found, verisol_counterexample = self.veriman.analyze_contract(self.inorder_config)
        self.check_error_output(proof_found, verisol_counterexample, ['Constructor'])


    def test_once_true(self):
        self.inorder_config.instrumentation.predicates = ['a_called -> once(num_calls > 0)']
        proof_found, verisol_counterexample = self.veriman.analyze_contract(self.inorder_config)
        self.assertFalse(proof_found)
        self.check_no_error_output(verisol_counterexample)


    def test_always_false(self):
        self.inorder_config.instrumentation.predicates = ['always(num_calls < 3)']
        proof_found, verisol_counterexample = self.veriman.analyze_contract(self.inorder_config)
        self.check_error_output(proof_found, verisol_counterexample, ['Constructor', 'a', 'a', 'a'])


    def test_always_true(self):
        self.inorder_config.instrumentation.predicates = ['always(num_calls >= 0)']
        proof_found, verisol_counterexample = self.veriman.analyze_contract(self.inorder_config)
        self.assertFalse(proof_found)
        self.check_no_error_output(verisol_counterexample)


    def test_parameters(self):
        params_config = TestVeriMan.get_test_config()
        params_config.contract.path = os.path.dirname(os.path.abspath(__file__)) + '/InOrderWithParams.sol'
        params_config.instrumentation.instrument = False

        proof_found, verisol_counterexample = self.veriman.analyze_contract(params_config)

        self.check_error_output(proof_found, ['Constructor', 'a', 'b', 'c'], verisol_counterexample)


    def test_instrumentation_only(self):
        contract_name = 'PaymentSplitter'
        instrumentation_only_config = TestVeriMan.get_test_config()
        instrumentation_only_config.contract.path = os.path.dirname(os.path.abspath(__file__)) + '/' + contract_name + '.sol'
        instrumentation_only_config.instrumentation.predicates = ['_totalReleased <= _totalShares', 'block.number > 10']
        instrumentation_only_config.verification.verisol.use = False

        proof_found, verisol_counterexample = self.veriman.analyze_contract(instrumentation_only_config)

        self.assertFalse(proof_found)
        self.check_no_error_output(verisol_counterexample)

        instrumented_file_name = contract_name + INSTRUMENTED_FILE_END

        self.check_contract_compiles(instrumented_file_name) # TODO check more

        os.remove(instrumented_file_name)


    def test_echidna_instrumentation(self):
        self.inorder_config.instrumentation.predicates = ['previously(b_called) -> c_called', 'b_called -> since(c_called, a_called)']
        self.inorder_config.instrumentation.for_echidna = True
        self.inorder_config.verification.verisol.use = False

        proof_found, verisol_counterexample = self.veriman.analyze_contract(self.inorder_config)

        # Restore test configs:
        self.inorder_config.instrumentation.for_echidna = False
        self.inorder_config.verification.verisol.use = True

        instrumented_file_name = 'InOrder' + INSTRUMENTED_FILE_END

        self.check_contract_compiles(instrumented_file_name) # TODO check more

        os.remove(instrumented_file_name)

    def test_inheritance(self):
        contract_name = 'Inheritance'
        inheritance_config = TestVeriMan.get_test_config()
        inheritance_config.contract.path = os.path.dirname(os.path.abspath(__file__)) + '/' + contract_name + '.sol'
        inheritance_config.contract.name = 'D'
        inheritance_config.instrumentation.predicates = ['a_var + b_var + c_var + d_var < 10']
        inheritance_config.verification.verisol.use = False

        proof_found, verisol_counterexample = self.veriman.analyze_contract(inheritance_config)

        instrumented_file_name = contract_name + INSTRUMENTED_FILE_END

        self.check_contract_compiles(instrumented_file_name)  # TODO check more

        os.remove(instrumented_file_name)