from slither.slither import Slither
from parser import Parser
import parser
import collections


# TODO move to constants file?
CONSTRUCTOR_NAME = 'constructor'


# This whole class is a prototype, a proper parser should be used


class Instrumentator:

    def instrument(self, contract_path, contract_name, predicates, instrument_for_echidna):
        self.contract_path = contract_path
        self.contract_name = contract_name

        slither = Slither(self.contract_path) # TODO check solc version
        self.contract_info = slither.get_contract_from_name(self.contract_name)
        if self.contract_info is None:
            raise Exception('Check config file for contract name')

        with open(self.contract_path) as contract_file:
            contract = contract_file.read()
        contract = contract.replace('}', '\n}')
        self.contract_lines = contract.split('\n')

        self.__pre_process_contract()

        parser = Parser()

        echidna_function = ''

        for index, predicate_string in enumerate(predicates):
            predicate = parser.parse(predicate_string)

            functions_to_instrument = self.__get_functions_to_instrument(predicate)

            self.__instrument_new_variables(predicate, functions_to_instrument, instrument_for_echidna)

            if instrument_for_echidna:
                echidna_function += '(' + predicate.solidity_repr + ')\n&& '
            else:
                assert_string = f'assert({predicate.solidity_repr}); // VERIMAN ASSERT FOR PREDICATE NO. {index + 1}'
                self.__insert_in_functions(functions_to_instrument, assert_string, self.__insert_at_end_of_functions)

        if instrument_for_echidna:
            echidna_function = 'function echidna_invariant() public returns(bool) {\nreturn ' \
                               + echidna_function.rsplit('\n&& ', 1)[0]\
                               + ';\n}'
            self.__insert_in_contract(echidna_function)

        contract = '\n'.join(self.contract_lines)
        with open(self.contract_path, 'w') as contract_file:
            contract_file.write(contract)


    def __pre_process_contract(self):
        pragma = ''
        pragma_found = False
        inside_contract = False
        constructor_found = False
        self.first_line_of_contract = 0
        self.last_line_of_contract = len(self.contract_lines)

        for index, line in enumerate(self.contract_lines):
            line_no_spaces = line.replace(' ', '')

            if not pragma_found and 'pragmasolidity' in line_no_spaces:
                pragma_found = True
                pragma = line_no_spaces.split('pragmasolidity')[1].split(';')[0]

            if line.lstrip().startswith('contract '):
                was_inside_contract = inside_contract
                inside_contract = line_no_spaces.startswith('contract' + self.contract_name)

                if inside_contract:
                    for i in range(index, len(self.contract_lines) - 1):
                        contract_line = self.contract_lines[i]
                        if '{' in contract_line:
                            self.first_line_of_contract = i # TODO test
                            break
                elif was_inside_contract:
                    self.last_line_of_contract = index # TODO test
                    break

            if inside_contract and (line_no_spaces.startswith(CONSTRUCTOR_NAME + '(') or
                                    line_no_spaces.startswith('function' + self.contract_name + '(')):
                constructor_found = True
                break

        if not constructor_found:
            if pragma.startswith('^0.4'):
                constructor_string = f'function {self.contract_name}() public {{\n}}'
            elif pragma.startswith('^0.5'):
                constructor_string = CONSTRUCTOR_NAME + '() public {\n}'
            else:
                # TODO handle cases like "pragma solidity >=0.4.0 <0.6.0;"
                raise Exception("Unknown pragma in contract")

            self.__insert_in_contract(constructor_string + ' // VERIMAN ADDED CONSTRUCTOR\n')

        self.__add_inherited_functions()


    def __should_be_instrumented(self, func):
        return not func.is_shadowed and func.visibility in ['public', 'internal'] # TODO check internal


    def __is_constructor(self, func):
        return func.is_constructor or func.is_constructor_variables


    def __add_inherited_functions(self):
        with open(self.contract_path) as original_contract_file:
            original_contract = original_contract_file.readlines()

        for func in self.contract_info.functions_inherited:
            if not self.__is_constructor(func) and self.__should_be_instrumented(func):
                function_declaration_start = 'function ' + func.name # FIXME
                new_function = ''

                func_line_numbers = func.source_mapping['lines']
                first_line_number = func_line_numbers[0]
                last_line_number = func_line_numbers[-1]

                for line_number in range(first_line_number, last_line_number):
                    new_function += original_contract[line_number - 1]
                    if '{' in new_function: # FIXME
                        break

                new_function = function_declaration_start + new_function.split(function_declaration_start, 1)[1]
                new_function = new_function.split('{', 1)[0] + '{\n'

                if func.return_type is not None:
                    new_function += 'return '

                new_function += f'super.{func.name}('

                for param in func.parameters:
                    new_function += param.name + ','

                new_function = new_function.rsplit(',', 1)[0] + ');\n} // VERIMAN ADDED INHERITED FUNCTION\n'

                self.__insert_in_contract(new_function)


    def __instrument_new_variables(self, predicate, functions_to_instrument, instrument_for_echidna):
        if predicate.operator == parser.PREVIOUSLY:
            if instrument_for_echidna:
                initialization_code = f'bool {predicate.solidity_vars[0]};'
                update_code = f'{predicate.solidity_vars[0]}={predicate.values[0].solidity_repr};'

                self.__insert_in_contract(initialization_code)
                self.__insert_in_functions(functions_to_instrument, update_code, self.__insert_at_beginning_of_functions)
            else:
                initialization_code = f'bool {predicate.solidity_vars[0]}={predicate.values[0].solidity_repr};'

                self.__insert_in_functions(functions_to_instrument, initialization_code, self.__insert_at_beginning_of_functions)
        elif predicate.operator == parser.SINCE:
            q = predicate.solidity_vars[0]
            p_since_q = predicate.solidity_vars[1]
            q_repr = predicate.values[1].solidity_repr
            p_repr = predicate.values[0].solidity_repr
            initialization_code = f'bool {q}=false;\nbool {p_since_q}=true;'
            update_code = '''if({q}){{\n\
{p_since_q}={p_repr}&&{p_since_q};\n\
}}\n
{q}={q_repr}||{q};\n'''.format(q=q, p_since_q=p_since_q, q_repr=q_repr, p_repr=p_repr)

            self.__insert_in_contract(initialization_code)
            self.__insert_in_functions(functions_to_instrument, update_code, self.__insert_at_end_of_functions)

        for term in predicate.values:
            self.__instrument_new_variables(term, functions_to_instrument, instrument_for_echidna)


    def __get_functions_to_instrument(self, predicate):
        functions_to_instrument = set()

        for variable_name in predicate.related_vars:

            if self.__is_solidity_property(variable_name):
                functions_to_instrument = set(self.contract_info.functions_entry_points)
            else:
                variable = self.contract_info.get_state_variable_from_name(variable_name)
                functions_writing_variable = self.contract_info.get_functions_writing_to_variable(variable)

                for func in functions_writing_variable:
                    if self.__should_be_instrumented(func):
                        functions_to_instrument.add(func)

                functions_to_instrument = functions_to_instrument.union(self.__get_public_callers(functions_writing_variable))

            if len(functions_to_instrument) == len(self.contract_info.functions_entry_points):
                break

        # The initial state also needs to be checked:
        is_constructor_considered = False # FIXME, temporal, issue with Slither
        for func in functions_to_instrument:
            if self.__is_constructor(func):
                is_constructor_considered = True
                break

        if not is_constructor_considered:
            if self.contract_info.constructor is not None:
                functions_to_instrument.add(self.contract_info.constructor)
            else:
                for func in self.contract_info.functions:
                    if self.__is_constructor(func):
                        functions_to_instrument.add(func)
                        break

        # We can thought of all no-state-changing functions as equivalent:
        for func in self.contract_info.functions:
            if not func in functions_to_instrument and not self.__is_constructor(func) and self.__should_be_instrumented(func):
                functions_to_instrument.add(func)
                break

        return functions_to_instrument


    def __is_solidity_property(self, variable_name):
        parts = variable_name.split('.')
        return parts[0] in ['block', 'msg', 'tx', 'this', 'now']


    def __get_public_callers(self, functions):
        result = set()

        for func in functions:
            callers, queue = set(), collections.deque([func])

            while queue:
                func_to_check = queue.popleft()

                for neighbour in func_to_check.reachable_from_functions:
                    if neighbour not in callers:
                        queue.append(neighbour)
                        callers.add(neighbour)

                        if self.__should_be_instrumented(neighbour):
                            result.add(neighbour)

        return result


    def __insert_in_contract(self, code_to_insert):
        self.contract_lines.insert(self.first_line_of_contract + 1, code_to_insert)
        self.last_line_of_contract += 1


    def __insert_in_functions(self, functions, code_string, insert_in_function):
        remaining_functions = list(functions)
        open_blocks = 0
        in_function = False
        current_function = None

        constructors_in_list = list(filter(lambda func: self.__is_constructor(func), remaining_functions))
        fallbacks_in_list = list(filter(lambda func: func.is_fallback, remaining_functions))

        if len(constructors_in_list) > 1 or len(fallbacks_in_list) > 1:
            raise Exception('Invalid set of functions to instrument')

        for index in range(self.first_line_of_contract, self.last_line_of_contract):
            line = self.contract_lines[index]
            open_blocks = open_blocks + line.count('{') - line.count('}')

            if open_blocks <= 2:
                line_stripped = line.lstrip()
                line_no_spaces = line.replace(' ', '')

                if line_stripped.startswith('function ') \
                        or line_no_spaces.startswith('function()') \
                        or line_no_spaces.startswith(CONSTRUCTOR_NAME + '('):

                    func_found = None

                    if (line_no_spaces.startswith(CONSTRUCTOR_NAME + '(') or line_no_spaces.startswith('function' + self.contract_name)) \
                            and len(constructors_in_list) > 0:
                        func_found = constructors_in_list[0]
                        constructors_in_list = []
                    elif line_no_spaces.startswith('function()') and len(fallbacks_in_list) > 0:
                        func_found = fallbacks_in_list[0]
                        fallbacks_in_list = []
                    else:
                        for func in remaining_functions:
                            if line_no_spaces.startswith('function' + func.name + '('):
                                func_found = func
                                break

                    found = func_found is not None
                    if found:
                        remaining_functions.remove(func_found)
                        current_function = func_found

                    in_function = found

            if in_function:
                function_done = insert_in_function(code_string, index, open_blocks, current_function)
                if function_done and len(remaining_functions) == 0:
                    break
                else:
                    in_function = not function_done

        if len(remaining_functions) > 0:
            raise Exception('One or more functions couldn\'t be instrumented')


    def __insert_at_beginning_of_functions(self, code_string, index, open_blocks, current_function):
        function_done = False
        line = self.contract_lines[index]

        if open_blocks <= 2 and '{' in line:
            self.contract_lines[index] = line.replace('{', '{\n' + code_string, 1)
            function_done = True

        return function_done


    def __insert_at_end_of_functions(self, code_string, index, open_blocks, current_function):
        function_done = False
        line = self.contract_lines[index]

        if 'return ' in line:
            if not 'return VERIMAN_' in line:
                store_return_values = ''
                return_variables = ''
                for type in current_function.return_type:
                    new_var_for_return_value = Parser.create_variable_name('return_value')
                    store_return_values += f'{type} {new_var_for_return_value},'
                    return_variables += new_var_for_return_value + ','
                store_return_values = store_return_values.rsplit(',', 1)[0]
                return_variables = return_variables.rsplit(',', 1)[0]

                if len(current_function.return_type) > 1:
                    store_return_values = '(' + store_return_values + ')'
                    return_variables = '(' + return_variables + ')'

                return_value = line.split('return ', 1)[1].split(';', 1)[0]

                assignment_line = f'{store_return_values}={return_value};'
                new_return_line = f'return {return_variables}'

                self.contract_lines[index] = line.replace(f'return {return_value}', f'{assignment_line}\n{code_string}\n{new_return_line}')
            else:
                self.contract_lines[index] = line.replace('return ', f'{code_string}\nreturn ')

            function_done = open_blocks <= 2

        if 'return;' in line:
            self.contract_lines[index] = line.replace('return;', f'{code_string}\nreturn;')
            function_done = open_blocks <= 2

        if not function_done and open_blocks == 1 and '}' in line:
            solidity_lines = line.split(';')
            finishes_with_return = 'return ' in solidity_lines[len(solidity_lines) - 1]
            if not finishes_with_return:
                self.contract_lines[index] =  (code_string + '\n}').join(line.rsplit('}', 1))
                function_done = True

        return function_done