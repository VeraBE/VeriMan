import os
import time
import subprocess
import commentjson
from types import SimpleNamespace as Namespace
from datetime import datetime
from manticore.ethereum import ManticoreEVM
from manticore.utils import config as ManticoreConfig
from manticore.ethereum.plugins import LoopDepthLimiter, FilterFunctions
from src.instrumentator import Instrumentator
from shutil import copyfile


class VeriMan:

    @staticmethod
    def parse_config(file_name):
        with open(file_name) as config_file:
            config_file_string = config_file.read()
            return commentjson.loads(config_file_string, object_hook=lambda d: Namespace(**d))


    def __init__(self):
        self.files_to_cleanup = set()


    def __del__(self):
        self.__cleanup()


    def pre_process_contract(self, config):
        start_time = time.time()

        self.contract_path = config.contract.path
        self.contract_args = config.contract.args
        self.contract_name = config.contract.name
        if len(self.contract_name) == 0:
            self.contract_name = self.contract_path.rsplit('/', 1)[1].replace('.sol', '')

        self.__read_config(config)

        self.print('[.] Pre processing', self.contract_name)

        self.__merge_contract()

        self.original_contract_path = self.contract_path

        if self.instrument:
            self.instrumentator = Instrumentator()

            self.instrumentator.pre_process_contract(self.contract_path, self.contract_name, solc_command=self.solc_command)

        end_time = time.time()

        self.print('[-] Pre processing time:', end_time - start_time, 'seconds')


    def analyze_contract(self, config, **kargs):
        reuse_pre_process = kargs.get('reuse_pre_process', False)

        if reuse_pre_process:
            self.__read_config(config)

            self.contract_path = self.original_contract_path.replace('.sol',
                                                                     '_' + datetime.now().strftime('%s') + '.sol')
            copyfile(self.original_contract_path, self.contract_path)
            if self.__contract_instrumented_should_be_removed():
                self.files_to_cleanup.add(self.contract_path)
        else:
            self.pre_process_contract(config)

        proof_found = False
        verisol_counterexample = []

        if self.instrument:
            self.print('[-] Will instrument to check:', self.predicates)

        if self.instrument:
            start_time = time.time()

            self.instrumentator.instrument(self.contract_path,
                                           self.contract_name,
                                           self.predicates,
                                           for_echidna=self.instrument_for_echidna,
                                           solc_command=self.solc_command,
                                           reuse_pre_process=True)

            end_time = time.time()

            self.print('[-] Instrumentation time:', end_time - start_time, 'seconds')

        if self.use_verisol:
            start_time = time.time()

            proof_found, verisol_counterexample = self.__run_verisol()

            trace_for_manticore = list(verisol_counterexample)
            if len(trace_for_manticore) > 0:
                trace_for_manticore.remove('Constructor')

            if self.use_manticore and len(trace_for_manticore) > 0:
                self.__run_manticore(trace_for_manticore)

            end_time = time.time()

            self.print('[-] Analysis time:', end_time - start_time, 'seconds')

        return proof_found, verisol_counterexample


    def __read_config(self, config):
        self.does_cleanup = config.output.cleanup
        self.verbose = config.output.verbose
        self.print = print if self.verbose else lambda *a, **k: None

        self.instrument = config.instrumentation.instrument
        self.instrument_for_echidna = config.instrumentation.for_echidna
        self.solc_command = config.instrumentation.solc_command
        self.predicates = config.instrumentation.predicates

        self.use_verisol = config.verification.verisol.use
        self.verisol_command = config.verification.verisol.command
        self.tx_limit = config.verification.verisol.txs_bound

        self.use_manticore = config.verification.manticore.use
        self.manticore_output_path = config.verification.manticore.output_path
        self.loop_limit = config.verification.manticore.loops
        self.procs = config.verification.manticore.procs
        self.user_initial_balance = config.verification.manticore.user_initial_balance
        self.avoid_constant_txs = config.verification.manticore.avoid_constant_txs
        self.force_loop_limit = config.verification.manticore.loop_delimiter
        self.amount_user_accounts = config.verification.manticore.user_accounts
        if self.use_manticore and self.amount_user_accounts < 1:
            raise Exception('At least one user account has to be created')
        self.fallback_data_size = config.verification.manticore.fallback_data_size


    def __merge_contract(self):
        # Solidity and VeriSol don't support imports, plus sol-merger removes comments

        solmerger_process = subprocess.Popen([f'sol-merger {self.contract_path}'], stdout=subprocess.PIPE, shell=True)
        solmerger_process.wait()
        solmerger_process.stdout.close()

        merged_path = self.contract_path.replace('.sol', '_merged.sol')

        if not os.path.isfile(merged_path):
            raise Exception('Contract merging failed, check imports')

        new_contract_path = self.contract_path.replace('.sol', '_VERIMAN_' + datetime.now().strftime('%s') + '.sol')
        os.rename(merged_path, new_contract_path)
        self.contract_path = new_contract_path

        if self.__contract_instrumented_should_be_removed():
            self.files_to_cleanup.add(self.contract_path)


    def __run_verisol(self):
        self.print('[.] Running VeriSol')

        verisol_command = f'{self.verisol_command} {self.contract_path} {self.contract_name} /txBound:{str(self.tx_limit)}'
        verisol_process = subprocess.Popen([verisol_command], stdout=subprocess.PIPE, shell=True)
        verisol_process.wait()
        verisol_output = str(verisol_process.stdout.read(), 'utf-8')
        verisol_process.stdout.close()

        proof_found = 'Proof found' in verisol_output
        counterexample = []
        self.files_to_cleanup.update(['__SolToBoogieTest_out.bpl', 'boogie.txt', 'corral.txt', 'corral_counterex.txt', 'corral_out.bpl', 'corral_out_trace.txt', 'error.bpl'])

        if proof_found:
            self.print('[!] Contract proven, asserts cannot fail')
        elif 'Found a counterexample' in verisol_output:
            trace_parts = verisol_output.split(self.contract_name + '::')
            del trace_parts[0]

            for part in trace_parts:
                call_found = part.split(' ', 1)[0]
                counterexample.append(call_found)
            self.print('[!] Counterexample found:', counterexample)
        elif 'Did not find a proof' in verisol_output:
            self.print('[!] Contract cannot be proven, but a counterexample was not found, successful up to', str(self.tx_limit), 'transactions')
        else:
            raise Exception('Error reported by VeriSol:\n' + verisol_output)

        return proof_found, counterexample


    def __run_manticore(self, trace):
        self.print('[.] Running Manticore')

        consts = ManticoreConfig.get_group('core')
        consts.procs = self.procs

        output_path = self.__create_output_path()
        manticore = ManticoreEVM(workspace_url=output_path)

        if self.force_loop_limit:
            loop_delimiter = LoopDepthLimiter(loop_count_threshold=self.loop_limit)
            manticore.register_plugin(loop_delimiter)

        if self.avoid_constant_txs:
            filter_nohuman_constants = FilterFunctions(regexp=r'.*', depth='human', mutability='constant', include=False)
            manticore.register_plugin(filter_nohuman_constants)

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
            if function_name == '': # FIXME, check VeriSol trace
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

        if len(throw_states) == 0:
            raise Exception('Manticore couldn\'t confirm the counterexample')

        if self.verbose:
            for state in throw_states:
                manticore.generate_testcase(state)

        self.print('[-] Look for full output in:', manticore.workspace)


    def __cleanup(self):
        if self.does_cleanup:
            self.print('[.] Cleaning up')
            for file in self.files_to_cleanup:
                if os.path.isfile(file):
                    os.remove(file)
            self.files_to_cleanup = set()


    def __create_output_path(self):
        output_folder = self.manticore_output_path
        if not os.path.exists(output_folder):
            os.mkdir(output_folder) # FIXME?

        output_path = output_folder + '/' + datetime.now().strftime('%s') + '_' + self.contract_name
        os.mkdir(output_path)

        return output_path


    def __contract_instrumented_should_be_removed(self):
        return not (self.instrument and not self.use_verisol)