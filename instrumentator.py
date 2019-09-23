from slither.slither import Slither
from parser import Parser
import parser
import collections


class Instrumentator:

    def instrument(self, contract_path, contract_name, predicates, instrument_for_echidna):
        self.contract_path = contract_path
        self.contract_name = contract_name

        slither = Slither(self.contract_path)
        self.contract_info = slither.get_contract_from_name(self.contract_name)
        if self.contract_info is None:
            raise Exception('Check config file for contract name')

        with open(self.contract_path) as contract_file:
            contract = contract_file.read()
        contract = contract.replace('}', '\n}') # FIXME
        self.contract_lines = contract.split('\n')

        parser = Parser()

        # FIXME "missing" constructor needs to be considered, fix when Solidity version is fixed
        # FIXME "missing" fallback function also needs to be considered

        # TODO refactor echidna instrumentation:
        if instrument_for_echidna:
            function_to_add = 'function echidna_invariant() public returns(bool) {\nreturn '

            for predicate_string in predicates:
                predicate = parser.parse(predicate_string)
                function_to_add += '(' + predicate.solidity_repr + ')\n&& '

                functions_to_instrument = self.__get_functions_to_instrument(predicate)
                self.__instrument_new_variables(predicate, functions_to_instrument, instrument_for_echidna)

            function_to_add = function_to_add.rsplit('\n&& ', 1)[0]
            function_to_add += ';\n}'
            self.__insert_in_contract(function_to_add)
        else:
            for index, predicate_string in enumerate(predicates):
                predicate = parser.parse(predicate_string)

                functions_to_instrument = self.__get_functions_to_instrument(predicate)

                self.__instrument_new_variables(predicate, functions_to_instrument, instrument_for_echidna)

                assert_string = f'assert({predicate.solidity_repr}); // VERIMAN ASSERT FOR PREDICATE NO. {index + 1}'
                self.__insert_in_functions(functions_to_instrument, assert_string, self.__insert_at_end_of_functions)

        contract = '\n'.join(self.contract_lines)
        with open(self.contract_path, 'w') as contract_file:
            contract_file.write(contract)


    def __instrument_new_variables(self, predicate, functions_to_instrument, instrument_for_echidna):
        if predicate.operator == parser.PREVIOUSLY:
            if instrument_for_echidna:
                initialization_code = f'bool {predicate.solidity_vars[0]};'
                update_code = f'{predicate.solidity_vars[0]} = {predicate.values[0].solidity_repr};'

                self.__insert_in_contract(initialization_code)
                self.__insert_in_functions(functions_to_instrument, update_code, self.__insert_at_beginning_of_functions)
            else:
                initialization_code = f'bool {predicate.solidity_vars[0]} = {predicate.values[0].solidity_repr};'

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
                    if func.visibility == 'public':
                        functions_to_instrument.add(func)

                functions_to_instrument = functions_to_instrument.union(self.__get_public_callers(functions_writing_variable))

            if len(functions_to_instrument) == len(self.contract_info.functions_entry_points):
                break

        # We can thought of all no-state-changing functions as equivalent:
        for func in self.contract_info.functions:
            if not func in functions_to_instrument:
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

                        if neighbour.visibility == 'public':
                            result.add(neighbour)

        return result


    def __insert_in_contract(self, initialization_string):
        in_contract = False

        for index, line in enumerate(self.contract_lines):
            in_contract = in_contract or 'contract ' in line
            if (in_contract and '{' in line) or ('contract ' and '{' in line):
                self.contract_lines[index] = line.replace('{', '{\n' + initialization_string)
                break


    def __insert_in_functions(self, functions, code_string, insert_in_function):
        remaining_functions = functions.copy()
        in_function = False
        open_blocks = 0
        current_function = None

        for index, line in enumerate(self.contract_lines):
            open_blocks = open_blocks + line.count('{') - line.count('}')

            if open_blocks <= 2:
                # TODO improve:

                line_stripped = line.lstrip()
                line_no_spaces = line.replace(' ', '')

                if line_stripped.startswith('function ') \
                        or line_no_spaces.startswith('function()') \
                        or line_no_spaces.startswith('constructor('):
                    found = False
                    for func in remaining_functions:
                        if line_no_spaces.startswith('function' + func.name + '(') \
                                or (func.name == 'fallback' and line_no_spaces.startswith('function()'))\
                                or (func.name == 'constructor' and (line_no_spaces.startswith('constructor(') or line_no_spaces.startswith('function' + self.contract_name + '('))):
                            found = True
                            remaining_functions.remove(func)
                            current_function = func
                            break

                    in_function = found

            if in_function:
                function_done = insert_in_function(code_string, index, open_blocks, current_function)
                if function_done and len(remaining_functions) == 0:
                    break
                else:
                    in_function = not function_done

        if len(remaining_functions) > 0:
            # FIXME temporal:

            not_constructor = None

            for func in remaining_functions:
                if func.name not in ['slitherConstructorVariables', 'fallback', 'constructor']:
                    not_constructor = func
                    break

            if not_constructor is not None:
                raise Exception('One or more functions couldn\'t be instrumented')


    def __insert_at_beginning_of_functions(self, code_string, index, open_blocks, current_function):
        function_done = False
        line = self.contract_lines[index]

        if ('function ' in line and '{' in line) or (open_blocks == 0 and '{' in line):
            self.contract_lines[index] = line.replace('{', '{\n' + code_string)
            function_done = True

        return function_done


    def __insert_at_end_of_functions(self, code_string, index, open_blocks, current_function):
        function_done = False
        line = self.contract_lines[index]

        if 'return ' in line:
            if not 'return VERIMAN_' in line:
                # For some versions of solc 'var' as a type is not enough:
                return_type = ''
                for type in current_function.return_type:
                    return_type += type.name + ', ' # TODO check
                return_type = return_type.rsplit(', ', 1)[0]
                new_var_for_return_value = Parser.create_variable_name('return_value')
                return_value = line.split('return ', 1)[1].split(';', 1)[0]

                assignment_line = f'{return_type} {new_var_for_return_value}={return_value};'
                new_return_line = f'return {new_var_for_return_value}'

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