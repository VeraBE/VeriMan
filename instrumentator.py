from slither.slither import Slither
from parser import Parser
import parser
import collections


# TODO refactor pre processing logic


class Instrumentator:

    def pre_process_contract(self, contract_path, contract_name):
        self.contract_path = contract_path
        self.contract_name = contract_name

        slither = Slither(self.contract_path)
        self.contract_info = slither.get_contract_from_name(self.contract_name)
        if self.contract_info is None:
            raise Exception('Check config file for contract name')

        with open(self.contract_path) as contract_file:
            self.contract_lines = contract_file.readlines()

        self.__add_constructor(slither)

        self.__add_inherited_functions()

        # TODO improve efficiency:

        with open(self.contract_path, 'w') as contract_file:
            contract_file.writelines(self.contract_lines)

        slither = Slither(self.contract_path)
        self.contract_info = slither.get_contract_from_name(self.contract_name)


    def instrument(self, contract_path, predicates, instrument_for_echidna):
        self.contract_path = contract_path

        with open(self.contract_path) as contract_file:
            self.contract_lines = contract_file.readlines()

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
                self.__insert_at_functions_end(functions_to_instrument, assert_string)

        if instrument_for_echidna:
            echidna_function = 'function echidna_invariant() public returns(bool) {\nreturn ' \
                               + echidna_function.rsplit('\n&& ', 1)[0]\
                               + ';\n}'
            self.__insert_in_contract(echidna_function)

        with open(self.contract_path, 'w') as contract_file:
            contract_file.writelines(self.contract_lines)


    def __should_be_instrumented(self, func):
        return not func.is_shadowed and \
               func.visibility in ['public', 'internal'] and \
               not (func.is_constructor and func.contract_declarer != self.contract_name) and \
               func.view is None and \
               func.name != 'slitherConstructorVariables'  # Because of Slither 'bug'


    def __add_constructor(self, slither):
        constructor_missing = self.contract_info.constructors_declared is None
        solc_version_parts = slither.solc_version.split('.')

        if constructor_missing:
            if int(solc_version_parts[0]) == 0 and int(solc_version_parts[1]) <= 4:
                constructor_string = f'function {self.contract_name}() public {{\n}}'
            else:
                constructor_string = 'constructor() public {\n}'

            self.__insert_in_contract('// VERIMAN ADDED CONSTRUCTOR:\n' + constructor_string)


    def __add_inherited_functions(self):
        for func in self.contract_info.functions_inherited:
            if not func.is_constructor and self.__should_be_instrumented(func):
                func_line_numbers = func.source_mapping['lines']
                first_line_number = func_line_numbers[0]
                last_line_number = func_line_numbers[-1]
                first_column_number = func.source_mapping['starting_column'] - 1

                new_function = ''

                for line_number in range(first_line_number - 1, last_line_number):
                    line = self.contract_lines[line_number]

                    if line_number == first_line_number - 1:
                        line = line[first_column_number : len(line) - 1]

                    new_function += line

                    if '{' in new_function:
                        break

                new_function = new_function.split('{', 1)[0] + '{\n'

                if func.return_type is not None:
                    new_function += 'return '

                new_function += f'super.{func.name}('

                for param in func.parameters:
                    new_function += param.name + ','

                new_function = new_function.rsplit(',', 1)[0] + ');\n}'

                self.__insert_in_contract('// VERIMAN ADDED INHERITED FUNCTION:\n' + new_function)


    def __instrument_new_variables(self, predicate, functions_to_instrument, instrument_for_echidna):
        if predicate.operator == parser.PREVIOUSLY:
            if instrument_for_echidna:
                initialization_code = f'bool {predicate.solidity_vars[0]};'
                update_code = f'{predicate.solidity_vars[0]}={predicate.values[0].solidity_repr};'

                self.__insert_in_contract(initialization_code)
                self.__insert_at_functions_beginning(functions_to_instrument, update_code)
            else:
                initialization_code = f'bool {predicate.solidity_vars[0]}={predicate.values[0].solidity_repr};'

                self.__insert_at_functions_beginning(functions_to_instrument, initialization_code)
        elif predicate.operator == parser.SINCE:
            q = predicate.solidity_vars[0]
            p_since_q = predicate.solidity_vars[1]
            q_repr = predicate.values[1].solidity_repr
            p_repr = predicate.values[0].solidity_repr
            initialization_code = f'bool {q}=false;\nbool {p_since_q}=true;'
            update_code = '''if({q}){{\n{p_since_q}={p_repr}&&{p_since_q};\n}}\n{q}={q_repr}||{q};'''\
                .format(q=q, p_since_q=p_since_q, q_repr=q_repr, p_repr=p_repr)

            self.__insert_in_contract(initialization_code)
            self.__insert_at_functions_end(functions_to_instrument, update_code)

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
        constructor = self.contract_info.constructor
        if constructor not in functions_to_instrument:
            functions_to_instrument.add(constructor)

        # We can thought of all no-state-changing functions as equivalent:
        # TODO create new one if necessary?
        for func in self.contract_info.functions:
            if self.__should_be_instrumented(func) and not func in functions_to_instrument:
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


    def __insert_in_contract(self, to_insert):
        self.__insert_at_beginning_of_structure(self.contract_info, to_insert + '\n')


    def __insert_at_functions_beginning(self, functions, to_insert):
        for func in functions:
            self.__insert_at_beginning_of_structure(func, to_insert)


    def __insert_at_beginning_of_structure(self, structure, to_insert):
        line_numbers = structure.source_mapping['lines']
        first_line_number = line_numbers[0]
        last_line_number = line_numbers[-1]

        for line_number in range(first_line_number - 1, last_line_number):
            line = self.contract_lines[line_number]

            if '{' in line:  # FIXME
                self.contract_lines[line_number] = line.replace('{', '{\n' + to_insert, 1)
                break


    def __insert_at_functions_end(self, functions, to_insert):
        for func in functions:
            func_line_numbers = func.source_mapping['lines']
            first_line_number = func_line_numbers[0]
            last_line_number = func_line_numbers[-1]
            done = False
            open_blocks = 0

            for line_number in range(first_line_number - 1, last_line_number):
                line = self.contract_lines[line_number]

                open_blocks = open_blocks + line.count('{') - line.count('}')

                if 'return ' in line:
                    if not 'return VERIMAN_' in line:
                        store_return_values = ''
                        return_variables = ''
                        for type in func.return_type:
                            new_var_for_return_value = Parser.create_variable_name('return_value')
                            store_return_values += f'{type} {new_var_for_return_value},'
                            return_variables += new_var_for_return_value + ','
                        store_return_values = store_return_values.rsplit(',', 1)[0]
                        return_variables = return_variables.rsplit(',', 1)[0]

                        if len(func.return_type) > 1:
                            store_return_values = '(' + store_return_values + ')'
                            return_variables = '(' + return_variables + ')'

                        return_value = line.split('return ', 1)[1].split(';', 1)[0]

                        assignment_line = f'{store_return_values}={return_value};'
                        new_return_line = f'return {return_variables}'

                        self.contract_lines[line_number] = line.replace(f'return {return_value}',
                                                                        f'{assignment_line}\n{to_insert}\n{new_return_line}') # FIXME
                    else:
                        self.contract_lines[line_number] = line.replace('return ', f'{to_insert}\nreturn ') # FIXME

                    done = done or open_blocks <= 1

                if 'return;' in line: # FIXME
                    self.contract_lines[line_number] = line.replace('return;', f'{to_insert}\nreturn;') # FIXME
                    done = done or open_blocks <= 1

                if open_blocks == 0 and not done: # FIXME
                    self.contract_lines[line_number] =  (to_insert + '\n}').join(line.rsplit('}', 1))