import os
import sys
import traceback
import re
import time
import config
from datetime import datetime
from manticore.ethereum import ManticoreEVM, DetectInvalid, ABI
from manticore.utils import config as manticoreConfig
from manticore.ethereum.plugins import LoopDepthLimiter, FilterFunctions, VerboseTraceStdout
from shutil import copyfile
from slither.slither import Slither


class VeriMan:

    def __init__(self):
        self.verisol_path = config.bins['verisol_path']
        self.corral_path = config.bins['corral_path']
        self.solc_path = config.bins['solc_path']

        self.contract_path = config.contract['path']
        self.contract_args = config.contract['args']
        self.contract_condition = config.contract['condition']
        self.fully_verify_condition = config.contract['fully_verify_condition']
        self.condition_line = config.contract['condition_line']

        self.condition_state = config.contract['state']
        if len(self.condition_state) == 0:
            self.condition_state = 'true'

        self.contract_name = config.contract['name']
        if len(self.contract_name) == 0:
            self.contract_name = self.contract_path.rsplit('/', 1)[1].replace('.sol', '')

        self.loop_limit = config.bounds['loops']
        self.tx_limit = config.bounds['txs']
        self.procs = config.bounds['procs']
        self.user_initial_balance = config.bounds['user_initial_balance']
        self.avoid_constant_txs = config.bounds['avoid_constant_txs']
        self.force_loop_limit = config.bounds['loop_delimiter']

        self.report_invalid = config.output['report_invalid']
        self.verbose = config.output['verbose']

        self.files_to_cleanup = []


    def analyze_contract(self):
        print('[-] Analyzing', self.contract_name)
        if self.fully_verify_condition or self.condition_line > 0:
            print('[-] Will check if', self.contract_condition, 'when ' + self.condition_state if self.condition_state != 'true' else '')

        self.pre_process_contract()

        try:
            start_time = time.time()
            trace = self.calculate_trace()
            self.execute_trace(trace)
            end_time = time.time()

            print('[-] Time elapsed:', end_time - start_time, 'seconds')
        except:
            info = sys.exc_info()
            print('[!] Unexpected exception:', info[1])
            traceback.print_tb(info[2])

        self.cleanup()


    def calculate_trace(self):
        print('[.] Calculating trace')

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

        print('[...] Creating a user account')
        user_account = manticore.create_account(balance=self.user_initial_balance)

        print('[...] Creating a contract and its library dependencies')
        source_code = self.get_contract_code(self.contract_path)
        try:
            contract_account = manticore.solidity_create_contract(source_code,
                                                                  owner=user_account,
                                                                  args=self.contract_args,
                                                                  contract_name=self.contract_name,
                                                                  solc_bin=self.solc_path)
        except:
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
                                      data=manticore.make_symbolic_buffer(320))
            else:
                function_to_call = getattr(contract_account, function_name)
                types = function_types[function_name]
                if len(types) > 0:
                    function_to_call(manticore.make_symbolic_arguments(function_types[function_name]))
                else:
                    function_to_call()

        self.show_results(manticore)

        print('[...] Finalizing')
        manticore.finalize(procs=self.procs)

        print('[-] Look for full Manticore results in', manticore.workspace)


    def pre_process_contract(self):
        modified_contract_path = self.contract_path.replace('.sol', '_toAnalyze.sol')

        copyfile(self.contract_path, modified_contract_path)
        self.files_to_cleanup.append(modified_contract_path)

        code_to_add = 'assert(' + self.contract_condition + ');'

        if self.condition_state != '':
            code_to_add = 'if (' + self.condition_state + ') ' + code_to_add

        if self.condition_line > 0:
            os.system("sed -i '" + str(self.condition_line) + 'i' + code_to_add + "' " + modified_contract_path)

        # Solidity and VeriSol don't support imports:
        os.system('sol-merger ' + modified_contract_path)
        self.contract_path = modified_contract_path.replace('.sol', '_merged.sol')
        self.files_to_cleanup.append(self.contract_path)

        if self.fully_verify_condition:
            slither = Slither(self.contract_path, solc=self.solc_path)
            main_contract = slither.get_contract_from_name(self.contract_name)
            variables_in_condition = self.get_variables_in_condition(self.contract_condition)
            related_functions = set()
            for variable_string in variables_in_condition:
                variable = main_contract.get_state_variable_from_name(variable_string)
                if variable != None:  # TODO improve
                    functions_writing_variable = main_contract.get_functions_writing_to_variable(variable)
                    related_functions = related_functions.union(self.get_public_callers(functions_writing_variable))

            self.append_to_every_function_end(related_functions, code_to_add)


    def get_public_callers(self, functions):
        # TODO function should be improved, this is a prototype

        result = set()

        for func in functions:
            if func.visibility == 'public':
                result.add(func.name)
            else:
                result = result.union(self.get_public_callers(func.reachable_from_functions))

        return result


    def append_to_every_function_end(self, function_names, code):
        # TODO function should be improved, this is a prototype
        # TODO "missing" constructor needs to be considered

        with open(self.contract_path) as contract_file:
            contract = contract_file.read()

        contract = contract.replace('}', '\n}')

        contract_lines = contract.split('\n')

        in_function = False
        open_blocks = 0
        for index, line in enumerate(contract_lines):
            if "function " in line:
                found = False
                for function_name in function_names:
                    if "function " + function_name in line:
                        found = True
                        break
                in_function = found

            if in_function:
                if "return " in line:
                    contract_lines[index] = line.replace('return ', code + '\nreturn ')

                open_blocks = open_blocks + line.count("{") - line.count("}")
                if open_blocks == 0:
                    contract_lines[index] = line.replace('}', code + '\n}')

        contract = '\n'.join(contract_lines)

        with open(self.contract_path, 'w') as contract_file:
            contract_file.write(contract)


    def get_variables_in_condition(self, condition):
        # TODO function should be improved, this is a prototype

        return re.findall('\w+', condition)


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


    def get_contract_code(self, contract_path):
        with open(contract_path, 'r') as contract_file:
            return contract_file.read()


    def show_results(self, manticore):
        throw_states = []
        for state in manticore.terminated_states:
            if str(state.context['last_exception']) == 'THROW':
                throw_states.append(state)

        message = 'that negates the given condition has been found:'
        print(('[!] No path ' if len(throw_states) == 0 else '[!] A path ') + message)

        state_num = 0
        for state in throw_states:
            print('[---] Path No. ' + str(state_num) + ':\n')
            blockchain = state.platform
            for sym_tx in blockchain.human_transactions:
                sys.stdout.write('Transactions No. %d\n' % blockchain.transactions.index(sym_tx))
                conc_tx = sym_tx.concretize(state)
                is_something_symbolic = sym_tx.dump(sys.stdout, state, manticore, conc_tx=conc_tx)
                if is_something_symbolic:
                    print('At least one value is symbolic and may take other values')
            state_num = state_num + 1


if __name__ == '__main__':
    veriman = VeriMan()
    veriman.analyze_contract()