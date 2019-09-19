import os
import config
import shutil
from unittest import TestCase
from veriman import VeriMan


class TestVeriMan(TestCase):

    # TODO improve test speed

    def setUp(self):
        test_config = config

        # TODO improve config read

        test_config.contract['path'] = os.path.dirname(os.path.abspath(__file__)).replace('/tests', '') + '/sample_contracts/InOrderHard.sol'
        test_config.contract['args'] = ()
        test_config.contract['name'] = 'InOrderHard'
        test_config.run['instrumentation'] = True
        test_config.run['trace'] = True
        test_config.bounds['loops'] = 5
        test_config.bounds['txs'] = 5
        test_config.bounds['procs'] = 3
        test_config.bounds['user_accounts'] = 2
        test_config.output['cleanup'] = True
        test_config.output['verbose'] = False
        test_config.output['really_verbose'] = False

        self.veriman = VeriMan(test_config)


    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(os.path.dirname(os.path.abspath(__file__)) + '/output')


    def check_error_output(self, actual_trace, expected_trace, error_states):
        # TODO confirm is the same as trace

        self.assertEqual(actual_trace, expected_trace)
        self.assertGreater(len(error_states), 0)


    def check_no_error_output(self, trace, error_states):
        self.assertEqual(len(trace), 0)
        self.assertEqual(len(error_states), 0)


    def test_integer_comparison_false(self):
        self.veriman.predicates = ['num_calls > 0']
        trace, error_states = self.veriman.analyze_contract()
        self.check_error_output(trace, ['a', 'b', 'b'], error_states)


    def test_integer_comparison_true(self):
        self.veriman.predicates = ['num_calls >= 0']
        trace, error_states = self.veriman.analyze_contract()
        self.check_no_error_output(trace, error_states)


    def test_implies_false(self):
        self.veriman.predicates = ['a_called -> b_called']
        trace, error_states = self.veriman.analyze_contract()
        self.check_error_output(trace, ['a'], error_states)


    def test_implies_true(self):
        self.veriman.predicates = ['b_called -> a_called']
        trace, error_states = self.veriman.analyze_contract()
        self.check_no_error_output(trace, error_states)


    def test_previously_false(self):
        self.veriman.predicates = ['previously(!a_called) && a_called']
        trace, error_states = self.veriman.analyze_contract()
        self.check_error_output(trace, ['a', 'a'], error_states)


    def test_previously_true(self):
        self.veriman.predicates = ['previously(num_calls >= 0) && (num_calls >= 0)']
        trace, error_states = self.veriman.analyze_contract()
        self.check_no_error_output(trace, error_states)


    def test_since_false(self):
        self.veriman.predicates = ['since(num_calls > 0, a_called)']
        trace, error_states = self.veriman.analyze_contract()
        self.check_error_output(trace, ['a', 'b', 'b'], error_states)


    def test_since_true(self):
        self.veriman.predicates = ['since(num_calls >= 0, a_called)']
        trace, error_states = self.veriman.analyze_contract()
        self.check_no_error_output(trace, error_states)


    def test_once_false(self):
        self.veriman.predicates = ['once(num_calls == 2)']
        trace, error_states = self.veriman.analyze_contract()
        self.check_error_output(trace, ['a'], error_states)


    def test_once_true(self):
        self.veriman.predicates = ['a_called -> once(num_calls > 0)']
        trace, error_states = self.veriman.analyze_contract()
        self.check_no_error_output(trace, error_states)


    def test_always_false(self):
        self.veriman.predicates = ['always(num_calls < 3)']
        trace, error_states = self.veriman.analyze_contract()
        self.check_error_output(trace, ['a', 'a', 'a'], error_states)


    def test_always_true(self):
        self.veriman.predicates = ['always(num_calls >= 0)']
        trace, error_states = self.veriman.analyze_contract()
        self.check_no_error_output(trace, error_states)