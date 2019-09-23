import os
import time
import subprocess
from datetime import datetime
from manticore.ethereum import ManticoreEVM, DetectInvalid, ABI
from manticore.utils import config as manticoreConfig
from manticore.ethereum.plugins import LoopDepthLimiter, FilterFunctions, VerboseTraceStdout
from shutil import copyfile
from instrumentator import Instrumentator



class VeriMan:

    def analyze_contract(self, config):
        self.__read_config(config)

        proof_found = False
        verisol_counterexample = []

        self.print('[-] Analyzing', self.contract_name)
        if self.instrument:
            self.print('[-] Will instrument to check:', self.predicates)

        self.__pre_process_contract()

        if self.verify:
            start_time = time.time()

            proof_found, verisol_counterexample = self.__run_verisol()

            if len(verisol_counterexample) > 0:
                self.__run_manticore(verisol_counterexample)

            end_time = time.time()

            self.print('[-] Time elapsed:', end_time - start_time, 'seconds')

        if self.does_cleanup:
            self.__cleanup()

        return proof_found, verisol_counterexample


    def __read_config(self, config):
        self.contract_path = config.contract.path
        self.contract_args = config.contract.args
        self.contract_name = config.contract.name
        if len(self.contract_name) == 0:
            self.contract_name = self.contract_path.rsplit('/', 1)[1].replace('.sol', '')

        self.does_cleanup = config.output.cleanup
        self.verbose = config.output.verbose
        self.print = print if self.verbose else lambda *a, **k: None

        self.instrument = config.instrumentation.instrument
        self.predicates = config.instrumentation.predicates

        self.verify = config.verification.verify

        self.verisol_path = config.verification.verisol.path
        self.tx_limit = config.verification.verisol.txs_bound

        self.loop_limit = config.verification.manticore.loops
        self.procs = config.verification.manticore.procs
        self.user_initial_balance = config.verification.manticore.user_initial_balance
        self.avoid_constant_txs = config.verification.manticore.avoid_constant_txs
        self.force_loop_limit = config.verification.manticore.loop_delimiter
        self.amount_user_accounts = config.verification.manticore.user_accounts
        if self.verify and self.amount_user_accounts < 1:
            raise Exception('At least one user account has to be created')
        self.fallback_data_size = config.verification.manticore.fallback_data_size

        self.files_to_cleanup = []


    def __pre_process_contract(self):
        modified_contract_path = self.contract_path.replace('.sol', '_toAnalyze.sol')

        copyfile(self.contract_path, modified_contract_path)
        self.files_to_cleanup.append(modified_contract_path)

        # Solidity and VeriSol don't support imports, plus sol-merger removes comments:
        os.system("sed -i '1ipragma solidity ^0.5;' " + modified_contract_path) # FIXME, temporal because of Manticore/Verisol version issues
        solmerger_process = subprocess.Popen([f'sol-merger {modified_contract_path}'], stdout=subprocess.PIPE, shell=True)
        solmerger_process.wait()
        solmerger_process.stdout.close()
        self.contract_path = modified_contract_path.replace('.sol', '_merged.sol')
        os.system("sed -i '1d' " + self.contract_path) # FIXME, temporal because of Manticore/Verisol version issues

        if not (self.instrument and not self.verify):
            self.files_to_cleanup.append(self.contract_path)

        if self.instrument:
            instrumentator = Instrumentator()
            instrumentator.instrument(self.contract_path, self.contract_name, self.predicates)


    def __run_verisol(self):
        self.print('[.] Running VeriSol')

        verisol_command = f'dotnet {self.verisol_path} {self.contract_path} {self.contract_name} /tryProof /tryRefutation:{str(self.tx_limit)} /printTransactionSequence'
        verisol_process = subprocess.Popen([verisol_command], stdout=subprocess.PIPE, shell=True)
        verisol_process.wait()
        verisol_output = str(verisol_process.stdout.read(), 'utf-8')
        verisol_process.stdout.close()

        proof_found = 'Proof found' in verisol_output
        counterexample = []

        if proof_found:
            self.files_to_cleanup += ['__SolToBoogieTest_out.bpl', 'boogie.txt']
            self.print('[!] Contract proven, asserts cannot fail')
        elif 'Found a counterexample' in verisol_output:
            self.files_to_cleanup += ['__SolToBoogieTest_out.bpl', 'boogie.txt', 'corral.txt', 'corral_counterex.txt', 'corral_out.bpl', 'corral_out_trace.txt']

            trace_parts = verisol_output.split(self.contract_name + '::')
            del trace_parts[0]

            for part in trace_parts:
                call_found = part.split(' ', 1)[0]
                if call_found not in ['Constructor']:
                    counterexample.append(call_found)
        elif 'Did not find a proof' in verisol_output:
            self.files_to_cleanup += ['__SolToBoogieTest_out.bpl', 'boogie.txt', 'corral.txt']
            self.print('[!] Contract cannot be proven, but a counterexample was not found, successful up to', str(self.tx_limit), 'transactions')
        else:
            raise Exception('Error reported by VeriSol:\n' + verisol_output)

        return proof_found, counterexample


    def __run_manticore(self, trace):
        self.print('[.] Running Manticore')

        consts = manticoreConfig.get_group('core')
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
        self.print('[.] Cleaning up')
        for file in self.files_to_cleanup:
            os.remove(file)
        self.files_to_cleanup = []


    def __create_output_path(self):
        output_folder = 'output'
        if not os.path.exists(output_folder):
            os.mkdir(output_folder)

        output_path = output_folder + '/' + datetime.now().strftime('%s') + '_' + self.contract_name
        os.mkdir(output_path)

        return output_path