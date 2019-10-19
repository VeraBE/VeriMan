import os
import shutil
import subprocess
from unittest import TestCase
from src.veriman import VeriMan
from slither.slither import Slither


class TestVeriMan(TestCase):

    @classmethod
    def setUpClass(cls):
        cls.inorder_config = TestVeriMan.get_test_config()
        cls.inorder_config.contract.path = os.path.dirname(os.path.abspath(__file__)) + '/InOrder.sol'
        cls.inorder_veriman = VeriMan()
        cls.inorder_veriman.pre_process_contract(cls.inorder_config)


    @classmethod
    def tearDownClass(cls):
        path_to_remove = cls.inorder_config.verification.manticore.output_path
        if os.path.isdir(path_to_remove):
            shutil.rmtree(path_to_remove)


    @staticmethod
    def get_test_config():
        test_config = VeriMan.parse_config('config_tests.json')
        user_config = VeriMan.parse_config('../config.json')
        test_config.verification.verisol.command = user_config.verification.verisol.command
        test_config.verification.manticore.output_path = os.path.dirname(os.path.abspath(__file__)) + '/output'
        return test_config


    def check_error_output(self, proof_found, actual_verisol_counterexample, expected_verisol_counterexample):
        self.assertFalse(proof_found)
        self.assertEqual(actual_verisol_counterexample, expected_verisol_counterexample)


    def check_no_error_output(self, verisol_counterexample):
        self.assertEqual(len(verisol_counterexample), 0)


    def check_contract_compiles(self, file_name):
        solc_process = subprocess.Popen(['solc ' + file_name],
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        shell=True)
        solc_process.wait()
        solc_process.stdout.close()
        solc_process.stderr.close()
        self.assertEqual(solc_process.returncode, 0)


    def test_integer_comparison_false(self):
        self.inorder_config.instrumentation.predicates = ['num_calls > 0']
        proof_found, verisol_counterexample = self.inorder_veriman.analyze_contract(self.inorder_config,
                                                                                    reuse_pre_process=True)
        self.check_error_output(proof_found, verisol_counterexample, ['Constructor'])


    def test_integer_comparison_true(self):
        self.inorder_config.instrumentation.predicates = ['num_calls >= 0']
        proof_found, verisol_counterexample = self.inorder_veriman.analyze_contract(self.inorder_config,
                                                                                    reuse_pre_process=True)
        self.assertFalse(proof_found)
        self.check_no_error_output(verisol_counterexample)


    def test_implies_false(self):
        self.inorder_config.instrumentation.predicates = ['a_called -> num_calls > 0']
        proof_found, verisol_counterexample = self.inorder_veriman.analyze_contract(self.inorder_config,
                                                                                    reuse_pre_process=True)
        self.check_error_output(proof_found, verisol_counterexample, ['Constructor', 'a', 'b', 'b'])


    def test_implies_true(self):
        self.inorder_config.instrumentation.predicates = ['b_called -> a_called']
        proof_found, verisol_counterexample = self.inorder_veriman.analyze_contract(self.inorder_config,
                                                                                    reuse_pre_process=True)
        self.assertTrue(proof_found)
        self.check_no_error_output(verisol_counterexample)


    def test_previously_false(self):
        self.inorder_config.instrumentation.predicates = ['previously(!a_called) && a_called']
        proof_found, verisol_counterexample = self.inorder_veriman.analyze_contract(self.inorder_config,
                                                                                    reuse_pre_process=True)
        self.check_error_output(proof_found, verisol_counterexample, ['Constructor'])


    def test_previously_true(self):
        self.inorder_config.instrumentation.predicates = ['previously(num_calls >= 0) && (num_calls >= 0)']
        proof_found, verisol_counterexample = self.inorder_veriman.analyze_contract(self.inorder_config,
                                                                                    reuse_pre_process=True)
        self.assertFalse(proof_found)
        self.check_no_error_output(verisol_counterexample)


    def test_since_false(self):
        self.inorder_config.instrumentation.predicates = ['since(num_calls > 0, a_called)']
        proof_found, verisol_counterexample = self.inorder_veriman.analyze_contract(self.inorder_config,
                                                                                    reuse_pre_process=True)
        self.check_error_output(proof_found, verisol_counterexample, ['Constructor'])


    def test_since_true(self):
        self.inorder_config.instrumentation.predicates = ['c_called -> since(num_calls >= 0, a_called)']
        proof_found, verisol_counterexample = self.inorder_veriman.analyze_contract(self.inorder_config,
                                                                                    reuse_pre_process=True)
        self.assertFalse(proof_found)
        self.check_no_error_output(verisol_counterexample)


    def test_once_false(self):
        self.inorder_config.instrumentation.predicates = ['once(num_calls == 2)']
        proof_found, verisol_counterexample = self.inorder_veriman.analyze_contract(self.inorder_config,
                                                                                    reuse_pre_process=True)
        self.check_error_output(proof_found, verisol_counterexample, ['Constructor'])


    def test_once_true(self):
        self.inorder_config.instrumentation.predicates = ['a_called -> once(num_calls > 0)']
        proof_found, verisol_counterexample = self.inorder_veriman.analyze_contract(self.inorder_config,
                                                                                    reuse_pre_process=True)
        self.assertFalse(proof_found)
        self.check_no_error_output(verisol_counterexample)


    def test_always_false(self):
        self.inorder_config.instrumentation.predicates = ['always(num_calls < 3)']
        proof_found, verisol_counterexample = self.inorder_veriman.analyze_contract(self.inorder_config,
                                                                                    reuse_pre_process=True)
        self.check_error_output(proof_found, verisol_counterexample, ['Constructor', 'a', 'a', 'a'])


    def test_always_true(self):
        self.inorder_config.instrumentation.predicates = ['always(num_calls >= 0)']
        proof_found, verisol_counterexample = self.inorder_veriman.analyze_contract(self.inorder_config,
                                                                                    reuse_pre_process=True)
        self.assertFalse(proof_found)
        self.check_no_error_output(verisol_counterexample)


    def test_echidna_instrumentation(self):
        self.inorder_config.instrumentation.predicates = ['previously(b_called) -> c_called',
                                                          'b_called -> since(c_called, a_called)']
        self.inorder_config.instrumentation.for_echidna = True
        self.inorder_config.verification.verisol.use = False

        proof_found, verisol_counterexample = self.inorder_veriman.analyze_contract(self.inorder_config,
                                                                                   reuse_pre_process=True)

        # Restore test configs:
        self.inorder_config.instrumentation.for_echidna = False
        self.inorder_config.verification.verisol.use = True

        self.check_contract_compiles(self.inorder_veriman.contract_path)

        slither = Slither(self.inorder_veriman.contract_path)
        contract_info = slither.get_contract_from_name('InOrder')
        echidna_invariants = list(filter(lambda func: func.name.startswith('echidna_'), contract_info.functions))

        self.assertEqual(len(echidna_invariants), 2)

        for invariant in echidna_invariants:
            self.assertEqual(invariant.return_type[0].name, 'bool')

        os.remove(self.inorder_veriman.contract_path)


    def test_parameters(self):
        params_config = TestVeriMan.get_test_config()
        params_config.contract.path = os.path.dirname(os.path.abspath(__file__)) + '/InOrderWithParams.sol'
        params_config.instrumentation.instrument = False

        veriman = VeriMan()
        proof_found, verisol_counterexample = veriman.analyze_contract(params_config)

        self.check_error_output(proof_found, ['Constructor', 'a', 'b', 'c'], verisol_counterexample)


    def test_inheritance(self):
        inheritance_config = TestVeriMan.get_test_config()
        inheritance_config.contract.path = os.path.dirname(os.path.abspath(__file__)) + '/Inheritance.sol'
        inheritance_config.contract.name = 'D'
        inheritance_config.instrumentation.predicates = ['a_var + b_var + c_var + d_var < 10', 'block.number > 10']
        inheritance_config.verification.verisol.use = False

        veriman = VeriMan()
        proof_found, verisol_counterexample = veriman.analyze_contract(inheritance_config)

        self.check_contract_compiles(veriman.contract_path)

        slither = Slither(veriman.contract_path)
        contract_info = slither.get_contract_from_name(inheritance_config.contract.name)

        expected_functions = set(list(['aFunction',
                                       'toBeOverwritten',
                                       'bFunction',
                                       'withTheSameName',
                                       'callsC',
                                       'dFunction',
                                       'constructor']))

        found_functions = list(map(lambda func: func.name, contract_info.functions_declared))

        self.assertEqual(found_functions.count('withTheSameName'), 3)
        self.assertEqual(found_functions.count('toBeOverwritten'), 1)

        self.assertEqual(expected_functions, set(found_functions))

        os.remove(veriman.contract_path)