import os
import config
import shutil
from unittest import TestCase
from veriman import VeriMan


class TestVeriMan(TestCase):

    # TODO improve test speed

    def setUp(self):
        # TODO improve config handling

        test_config = config
        test_config.contract['path'] = os.path.dirname(os.path.abspath(__file__)) + '/InOrderHard.sol'
        test_config.contract['args'] = ()
        test_config.contract['name'] = 'InOrderHard'
        test_config.output['cleanup'] = True
        test_config.output['verbose'] = False
        test_config.output['really_verbose'] = False
        test_config.instrumentation['instrument'] = True
        test_config.verification['verify'] = True
        test_config.verification['txs'] = 5
        test_config.verification['procs'] = 3
        test_config.verification['user_accounts'] = 2

        self.veriman = VeriMan(test_config)


    @classmethod
    def tearDownClass(cls):
        path_to_remove = os.path.dirname(os.path.abspath(__file__)) + '/output'
        if os.path.isdir(path_to_remove):
            shutil.rmtree(path_to_remove)


    def check_error_output(self, proof_found, actual_verisol_counterexample, expected_verisol_counterexample, manticore_counterexample):
        self.assertFalse(proof_found)
        self.assertEqual(actual_verisol_counterexample, expected_verisol_counterexample)
        self.assertGreater(len(manticore_counterexample), 0)

        manticore_counterexample_copy = manticore_counterexample.copy()
        del manticore_counterexample_copy[0] # Don't consider constructor

        for index, manticore_call in enumerate(manticore_counterexample_copy):
            function_name = manticore_call.split('(', 1)[0]
            self.assertEqual(function_name, actual_verisol_counterexample[index])


    def check_no_error_output(self, verisol_counterexample, manticore_counterexample):
        self.assertEqual(len(verisol_counterexample), 0)
        self.assertEqual(len(manticore_counterexample), 0)


    def test_integer_comparison_false(self):
        self.veriman.predicates = ['num_calls > 0']
        proof_found, verisol_counterexample, manticore_counterexample = self.veriman.analyze_contract()
        self.check_error_output(proof_found, verisol_counterexample, ['a', 'b', 'b'], manticore_counterexample)


    def test_integer_comparison_true(self):
        self.veriman.predicates = ['num_calls >= 0']
        proof_found, verisol_counterexample, manticore_counterexample = self.veriman.analyze_contract()
        self.assertFalse(proof_found)
        self.check_no_error_output(verisol_counterexample, manticore_counterexample)


    def test_implies_false(self):
        self.veriman.predicates = ['a_called -> b_called']
        proof_found, verisol_counterexample, manticore_counterexample = self.veriman.analyze_contract()
        self.check_error_output(proof_found, verisol_counterexample, ['a'], manticore_counterexample)


    def test_implies_true(self):
        self.veriman.predicates = ['b_called -> a_called']
        proof_found, verisol_counterexample, manticore_counterexample = self.veriman.analyze_contract()
        self.assertTrue(proof_found)
        self.check_no_error_output(verisol_counterexample, manticore_counterexample)


    def test_previously_false(self):
        self.veriman.predicates = ['previously(!a_called) && a_called']
        proof_found, verisol_counterexample, manticore_counterexample = self.veriman.analyze_contract()
        self.check_error_output(proof_found, verisol_counterexample, ['a', 'a'], manticore_counterexample)


    def test_previously_true(self):
        self.veriman.predicates = ['previously(num_calls >= 0) && (num_calls >= 0)']
        proof_found, verisol_counterexample, manticore_counterexample = self.veriman.analyze_contract()
        self.assertFalse(proof_found)
        self.check_no_error_output(verisol_counterexample, manticore_counterexample)


    def test_since_false(self):
        self.veriman.predicates = ['since(num_calls > 0, a_called)']
        proof_found, verisol_counterexample, manticore_counterexample = self.veriman.analyze_contract()
        self.check_error_output(proof_found, verisol_counterexample, ['a', 'b', 'b'], manticore_counterexample)


    def test_since_true(self):
        self.veriman.predicates = ['since(num_calls >= 0, a_called)']
        proof_found, verisol_counterexample, manticore_counterexample = self.veriman.analyze_contract()
        self.assertFalse(proof_found)
        self.check_no_error_output(verisol_counterexample, manticore_counterexample)


    def test_once_false(self):
        self.veriman.predicates = ['once(num_calls == 2)']
        proof_found, verisol_counterexample, manticore_counterexample = self.veriman.analyze_contract()
        self.check_error_output(proof_found, verisol_counterexample, ['a'], manticore_counterexample)


    def test_once_true(self):
        self.veriman.predicates = ['a_called -> once(num_calls > 0)']
        proof_found, verisol_counterexample, manticore_counterexample = self.veriman.analyze_contract()
        self.assertFalse(proof_found)
        self.check_no_error_output(verisol_counterexample, manticore_counterexample)


    def test_always_false(self):
        self.veriman.predicates = ['always(num_calls < 3)']
        proof_found, verisol_counterexample, manticore_counterexample = self.veriman.analyze_contract()
        self.check_error_output(proof_found, verisol_counterexample, ['a', 'a', 'a'], manticore_counterexample)


    def test_always_true(self):
        self.veriman.predicates = ['always(num_calls >= 0)']
        proof_found, verisol_counterexample, manticore_counterexample = self.veriman.analyze_contract()
        self.assertFalse(proof_found)
        self.check_no_error_output(verisol_counterexample, manticore_counterexample)


    def test_parameters(self):
        contract_name = 'InOrderWithParams'

        params_config = config
        params_config.contract['path'] = os.path.dirname(os.path.abspath(__file__)) + '/' + contract_name + '.sol'
        params_config.contract['name'] = contract_name
        params_config.output['cleanup'] = True
        params_config.output['verbose'] = False
        params_config.output['really_verbose'] = False
        params_config.instrumentation['instrument'] = False
        params_config.verification['verify'] = True

        veriman_params = VeriMan(params_config)

        proof_found, verisol_counterexample, manticore_counterexample = veriman_params.analyze_contract()

        self.check_error_output(proof_found, ['a', 'b', 'c'], verisol_counterexample, manticore_counterexample)

        self.assertEqual(len(manticore_counterexample), 4)

        first_call_parameter = manticore_counterexample[1].split('(', 1)[1].split(',')[0]
        second_call_paramter = manticore_counterexample[2].split('(', 1)[1].split(',')[0]
        third_call_parameter = manticore_counterexample[3].split('(', 1)[1].split(',')[0]

        self.assertGreater(int(first_call_parameter), 100)
        self.assertLess(int(second_call_paramter), 20)
        self.assertTrue(int(third_call_parameter) in [40, 43])


    def test_instrumentation_only(self):
        contract_name = 'PaymentSplitter'

        instrumentation_only_config = config
        instrumentation_only_config.contract['path'] = os.path.dirname(os.path.abspath(__file__)) + '/' + contract_name + '.sol'
        instrumentation_only_config.contract['name'] = contract_name
        instrumentation_only_config.output['cleanup'] = True
        instrumentation_only_config.output['verbose'] = False
        instrumentation_only_config.output['really_verbose'] = False
        instrumentation_only_config.instrumentation['instrument'] = True
        instrumentation_only_config.instrumentation['predicates'] = ['_totalReleased <= _totalShares']
        instrumentation_only_config.verification['verify'] = False

        veriman_instrumentation_only = VeriMan(instrumentation_only_config)

        proof_found, verisol_counterexample, manticore_counterexample = veriman_instrumentation_only.analyze_contract()

        self.assertFalse(proof_found)
        self.check_no_error_output(verisol_counterexample, manticore_counterexample) # FIXME

        instrumented_file_name = contract_name + '_toAnalyze_merged.sol'

        self.assertTrue(os.path.isfile(instrumented_file_name))

        # TODO check more

        os.remove(instrumented_file_name)