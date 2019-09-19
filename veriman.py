import os
import sys
import traceback
import time
import config
from datetime import datetime
from manticore.ethereum import ManticoreEVM, DetectInvalid
from manticore.utils import config as manticoreConfig
from manticore.ethereum.plugins import LoopDepthLimiter, FilterFunctions, VerboseTraceStdout
from shutil import copyfile
from instrumentator import Instrumentator


class VeriMan:

    def __init__(self, config):
        # TODO improve config read

        self.verisol_path = config.bins['verisol_path']

        self.run_instrumentation = config.run['instrumentation']
        self.predicates = config.run['predicates']
        self.run_trace = config.run['trace']

        self.contract_path = config.contract['path']
        self.contract_args = config.contract['args']

        self.contract_name = config.contract['name']
        if len(self.contract_name) == 0:
            self.contract_name = self.contract_path.rsplit('/', 1)[1].replace('.sol', '')

        self.loop_limit = config.bounds['loops']
        self.tx_limit = config.bounds['txs']
        self.procs = config.bounds['procs']
        self.user_initial_balance = config.bounds['user_initial_balance']
        self.avoid_constant_txs = config.bounds['avoid_constant_txs']
        self.force_loop_limit = config.bounds['loop_delimiter']
        self.amount_user_accounts = config.bounds['user_accounts']
        if self.amount_user_accounts < 1:
            raise Exception('At least one user account has to be created')
        self.fallback_data_size = config.bounds['fallback_data_size']

        self.report_invalid = config.output['report_invalid']
        self.does_cleanup = config.output['cleanup']
        self.really_verbose = config.output['really_verbose']
        self.verbose = config.output['verbose']
        self.print = print if self.verbose else lambda *a, **k: None

        self.files_to_cleanup = []


    def analyze_contract(self):
        trace = []
        error_states = []

        self.print('[-] Analyzing', self.contract_name)
        if self.run_instrumentation:
            self.print('[-] Will instrument to check: ', self.predicates)

        try:
            self.pre_process_contract()

            if self.run_trace:
                start_time = time.time()

                trace = self.calculate_trace()

                if len(trace) > 0:
                    error_states = self.execute_trace(trace)
                    if len(error_states) < 1:
                        self.print('[!] VeriSol found an error trace but Manticore couldn\'t confirm it')

                end_time = time.time()

                self.print('[-] Time elapsed:', end_time - start_time, 'seconds')
        except:
            info = sys.exc_info()
            self.print('[!] Unexpected exception:\n', info[1])
            if self.really_verbose:
                traceback.print_tb(info[2])

        if self.does_cleanup:
            self.cleanup()

        return trace, error_states


    def pre_process_contract(self):
        modified_contract_path = self.contract_path.replace('.sol', '_toAnalyze.sol')

        copyfile(self.contract_path, modified_contract_path)
        self.files_to_cleanup.append(modified_contract_path)

        # Solidity and VeriSol don't support imports, plus sol-merger removes comments:
        os.system("sed -i '1ipragma solidity ^0.5;' " + modified_contract_path) # FIXME, temporal for sol-merger
        os.system('sol-merger ' + modified_contract_path)
        self.contract_path = modified_contract_path.replace('.sol', '_merged.sol')
        # FIXME temporal, VeriSol and Manticore don't support the same version, VeriSol needs 0.5.10 and Manticore a version prior to 0.5:
        os.system("sed -i '1d' " + self.contract_path)

        if not (self.run_instrumentation and not self.run_trace):
            self.files_to_cleanup.append(self.contract_path)

        if self.run_instrumentation:
            instrumentator = Instrumentator()
            instrumentator.instrument(self.contract_path, self.contract_name, self.predicates)


    def calculate_trace(self):
        self.print('[.] Calculating trace')

        verisol_output = 'verisol_output.txt'
        self.files_to_cleanup += [verisol_output]

        os.system('dotnet ' + self.verisol_path + ' ' + self.contract_path + ' ' + self.contract_name + ' /tryProof /tryRefutation:' + str(self.tx_limit) + ' /printTransactionSequence > ' + verisol_output + ' 2> /dev/null')

        calls = []

        with open(verisol_output) as verisol_output_file:
            verisol_output_string = verisol_output_file.read()

        if 'Proof found' in verisol_output_string:
            self.files_to_cleanup += ['__SolToBoogieTest_out.bpl', 'boogie.txt']
            self.print('[!] Contract proven, asserts cannot fail')
        elif 'Found a counterexample' in verisol_output_string:
            self.files_to_cleanup += ['__SolToBoogieTest_out.bpl', 'boogie.txt', 'corral.txt', 'corral_counterex.txt', 'corral_out.bpl', 'corral_out_trace.txt']

            trace_parts = verisol_output_string.split(self.contract_name + '::')

            for part in trace_parts:
                call_found = part.split(' ', 1)[0]
                if call_found not in ['Command', 'Constructor']:
                    calls.append(call_found)
        elif 'Did not find a proof' in verisol_output_string:
            self.files_to_cleanup += ['__SolToBoogieTest_out.bpl', 'boogie.txt', 'corral.txt']
            self.print('[!] Contract cannot be proven, but a counterexample was not found, successful up to', str(self.tx_limit), 'transactions')
        else:
            self.print('[!] Error reported by VeriSol:\n', verisol_output_string)

        return calls


    def execute_trace(self, trace):
        self.print('[.] Executing trace')

        consts = manticoreConfig.get_group('core')
        consts.procs = self.procs

        output_path = self.get_output_path()
        manticore = ManticoreEVM(workspace_url=output_path)

        if self.really_verbose:
            manticore.verbosity(5)  # 5 is the max level
            verbose_plugin = VerboseTraceStdout()
            manticore.register_plugin(verbose_plugin)

        if self.force_loop_limit:
            loop_delimiter = LoopDepthLimiter(loop_count_threshold=self.loop_limit)
            manticore.register_plugin(loop_delimiter)

        if self.avoid_constant_txs:
            filter_nohuman_constants = FilterFunctions(regexp=r'.*', depth='human', mutability='constant', include=False)
            manticore.register_plugin(filter_nohuman_constants)

        if self.report_invalid:
            invalid_detector = DetectInvalid()
            manticore.register_detector(invalid_detector)

        self.print('[...] Creating user accounts')
        for num in range(0, self.amount_user_accounts):
            account_name = 'user_account_' + str(num)
            manticore.create_account(balance=self.user_initial_balance, name=account_name)

        self.print('[...] Creating a contract and its library dependencies')
        with open(self.contract_path, 'r') as contract_file:
            source_code = contract_file.read()
        try:
            contract_account = manticore.solidity_create_contract(source_code,
                                                                  owner=manticore.get_account('user_account_0'),
                                                                  args=self.contract_args,
                                                                  contract_name=self.contract_name)
        except:
            raise Exception('Check contract arguments')

        if contract_account is None:
            raise Exception('Contract account is None, check contract arguments')

        self.print('[...] Calling functions in trace')

        function_types = {}

        function_signatures = manticore.get_metadata(contract_account).function_signatures
        for signature in function_signatures:
            signature_parts = signature.split('(')
            name = str(signature_parts[0])
            types = str(signature_parts[1].replace(')', ''))
            function_types[name] = types

        for function_name in trace:
            if function_name == '':
                manticore.transaction(caller=manticore.make_symbolic_address(),
                                      address=contract_account,
                                      value=manticore.make_symbolic_value(),
                                      data=manticore.make_symbolic_buffer(self.fallback_data_size))
            else:
                function_to_call = getattr(contract_account, function_name)
                types = function_types[function_name]
                if len(types) > 0:
                    function_to_call(manticore.make_symbolic_arguments(function_types[function_name]))
                else:
                    function_to_call()

        self.print('[...] Processing output')

        throw_states = []
        for state in manticore.terminated_states:
            if str(state.context['last_exception']) == 'THROW':
                throw_states.append(state)

        message = 'that negates a predicate or a preexisting assert has been found.'
        self.print(('[!] No path ' if len(throw_states) == 0 else '[!] A path ') + message)

        if self.verbose:
            for state in throw_states:
                manticore.generate_testcase(state)

        self.print('[-] Look for full output in:', manticore.workspace)

        return throw_states


    def cleanup(self):
        self.print('[.] Cleaning up')
        for file in self.files_to_cleanup:
            os.remove(file)
        self.files_to_cleanup = []


    def get_output_path(self):
        output_folder = 'output'
        if not os.path.exists(output_folder):
            os.mkdir(output_folder)

        output_path = output_folder + '/' + datetime.now().strftime('%s') + '_' + self.contract_name
        os.mkdir(output_path)

        return output_path


if __name__ == '__main__':
    veriman = VeriMan(config)
    trace, error_states = veriman.analyze_contract()