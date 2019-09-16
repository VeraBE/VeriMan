import os
import sys
import traceback
import re
import time
import config
from datetime import datetime
from manticore.ethereum import ManticoreEVM, DetectInvalid
from manticore.utils import config as manticoreConfig
from manticore.ethereum.plugins import LoopDepthLimiter, FilterFunctions, VerboseTraceStdout
from shutil import copyfile
from instrumentator import Instrumentator


class VeriMan:

    def __init__(self):
        self.verisol_path = config.bins['verisol_path']
        self.corral_path = config.bins['corral_path']

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
        self.verbose = config.output['verbose']
        self.does_cleanup = config.output['cleanup']

        self.files_to_cleanup = []


    def analyze_contract(self):
        print('[-] Analyzing', self.contract_name)
        if self.run_instrumentation:
            print('[-] Will instrument to check: ', self.predicates)

        try:
            self.pre_process_contract()

            if self.run_trace:
                start_time = time.time()
                trace = self.calculate_trace()
                self.execute_trace(trace)
                end_time = time.time()

                print('[-] Time elapsed:', end_time - start_time, 'seconds')
        except:
            info = sys.exc_info()
            print('[!] Unexpected exception:\n', info[1])
            traceback.print_tb(info[2])

        if self.does_cleanup:
            self.cleanup()


    def calculate_trace(self):
        print('[.] Calculating trace')

        # TODO replace for new VeriSol command:

        print('[...] Generating intermediate representation')
        boogie_output = self.contract_name + '_Boogie.bpl'
        boogie_file = open(boogie_output, 'a+')  # Creates file if it doesn't exist, SolToBoogie needs an existing file
        self.files_to_cleanup.append(boogie_output)
        os.system('dotnet ' + self.verisol_path + '/Sources/SolToBoogie/bin/Debug/netcoreapp2.2/SolToBoogie.dll ' + self.contract_path + ' ' + self.verisol_path + ' ' + boogie_output)
        boogie_file_first_char = boogie_file.read(1)
        boogie_file.close()
        if len(boogie_file_first_char) == 0:
            raise Exception('Error generating intermediate representation')

        print('[...] Analysing')
        corral_output = self.contract_name + '_Corral.txt'
        self.files_to_cleanup.append(corral_output)
        os.system('mono ' + self.corral_path + '/corral.exe /recursionBound:' + str(self.loop_limit) + ' /k:' + str(self.tx_limit) + ' /main:CorralEntry_' + self.contract_name + ' /tryCTrace ' + boogie_output + ' /printDataValues:1 1> ' + corral_output)

        corral_trace = 'corral_out_trace.txt'

        if not os.path.isfile(corral_trace):
            with open(corral_output) as corral_output_file:
                corral_lines = corral_output_file.readlines()
                corral_message = ''.join(corral_lines)
                raise Exception('Analysis error\n' + corral_message)
        else:
            self.files_to_cleanup.append('corral_out.bpl')
            self.files_to_cleanup.append(corral_trace)

        with open(corral_trace) as corral_trace_file:
            corral_calls = corral_trace_file.read().split('CALL CorralChoice_' + self.contract_name)

        calls = []

        for corral_call in corral_calls:
            call_found = re.search('\ (\S*?)_', corral_call).group(1)
            if call_found != self.contract_name:
                calls.append(call_found)

        return calls


    def execute_trace(self, trace):
        if len(trace) == 0:
            print('[!] No trace to execute has been found')
            return

        print('[.] Executing trace')

        consts = manticoreConfig.get_group('core')
        consts.procs = self.procs

        output_path = self.get_output_path()
        manticore = ManticoreEVM(workspace_url=output_path)

        if self.verbose:
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

        print('[...] Creating user accounts')
        for num in range(0, self.amount_user_accounts):
            account_name = 'user_account_' + str(num)
            manticore.create_account(balance=self.user_initial_balance, name=account_name)

        print('[...] Creating a contract and its library dependencies')
        with open(self.contract_path, 'r') as contract_file:
            source_code = contract_file.read()
        try:
            contract_account = manticore.solidity_create_contract(source_code,
                                                                  owner=manticore.get_account('user_account_0'),
                                                                  args=self.contract_args,
                                                                  contract_name=self.contract_name)
        except:
            info = sys.exc_info()
            print('[!] Unexpected exception:\n', info[1])
            traceback.print_tb(info[2])
            raise Exception('Check contract arguments')

        if contract_account is None:
            raise Exception('Contract account is None, check contract arguments')

        print('[...] Calling functions in trace')

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

        print('[...] Processing output')
        self.output_results(manticore)


    def pre_process_contract(self):
        modified_contract_path = self.contract_path.replace('.sol', '_toAnalyze.sol')

        copyfile(self.contract_path, modified_contract_path)
        self.files_to_cleanup.append(modified_contract_path)

        # Solidity and VeriSol don't support imports:
        os.system("sed -i '1ipragma solidity ^0.5;' " + modified_contract_path) # FIXME, temporal for sol-merger
        os.system('sol-merger ' + modified_contract_path)
        self.contract_path = modified_contract_path.replace('.sol', '_merged.sol')
        os.system("sed -i '1d' " + self.contract_path) # FIXME temporal, while VeriSol and Manticore don't support the same version
        self.files_to_cleanup.append(self.contract_path)

        if self.run_instrumentation:
            instrumentator = Instrumentator()
            instrumentator.instrument(self.contract_path, self.contract_name, self.predicates)


    def cleanup(self):
        print('[.] Cleaning up')
        for file in self.files_to_cleanup:
            os.remove(file)


    def get_output_path(self):
        output_folder = 'output'
        if not os.path.exists(output_folder):
            os.mkdir(output_folder)

        output_path = output_folder + '/' + datetime.now().strftime('%s') + '_' + self.contract_name
        os.mkdir(output_path)

        return output_path


    def output_results(self, manticore):
        throw_states = []
        for state in manticore.terminated_states:
            if str(state.context['last_exception']) == 'THROW':
                throw_states.append(state)

        message = 'that negates the given condition or a preexisting has been found.'
        print(('[!] No path ' if len(throw_states) == 0 else '[!] A path ') + message)

        for state in throw_states:
            manticore.generate_testcase(state)

        print('[-] Look for full output in: ' + manticore.workspace)


if __name__ == '__main__':
    veriman = VeriMan()
    veriman.analyze_contract()