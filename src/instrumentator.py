from slither.slither import Slither
from src.parser import Parser
import src.parser as parser
import collections


class Instrumentator:

    def pre_process_contract(self, contract_path, contract_name, **kargs):
        self.contract_path = contract_path
        self.contract_name = contract_name
        solc_command = kargs.get('solc_command', 'solc')

        slither = Slither(self.contract_path, solc=solc_command)
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

        slither = Slither(self.contract_path, solc=solc_command)
        self.contract_info = slither.get_contract_from_name(self.contract_name)


    def instrument(self, contract_path, contract_name, predicates, **kargs):
        instrument_for_echidna = kargs.get('for_echidna', False)
        reuse_pre_process = kargs.get('reuse_pre_process', False)
        solc_command = kargs.get('solc_command', 'solc')

        if reuse_pre_process:
            self.contract_path = contract_path
        else:
            self.pre_process_contract(contract_path, contract_name, solc_command=solc_command)

        with open(self.contract_path) as contract_file:
            self.contract_lines = contract_file.readlines()

        parser = Parser()

        for index, predicate_string in enumerate(predicates):
            predicate = parser.parse(predicate_string)

            functions_to_instrument = self.__get_functions_to_instrument(predicate)

            # TODO refactor Echidna handling:
            modifier_body = self.__instrument_new_variables(predicate, '_;\n', functions_to_instrument, instrument_for_echidna)

            if instrument_for_echidna:
                echidna_function = f'function echidna_VERIMAN_predicate_no_{str(index + 1)}() public returns(bool){{\nreturn {predicate.solidity_repr};\n}}'
                self.__insert_in_contract(echidna_function)
            else:
                assert_string = f'assert({predicate.solidity_repr});'
                modifier_body = modifier_body + assert_string
                modifier_name = f'VERIMAN_predicate_{str(index + 1)}'
                modifier = f'modifier VERIMAN_predicate_{str(index + 1)}(){{\n{modifier_body}\n}}'

                self.__insert_in_contract(modifier)
                self.__insert_as_modifier(functions_to_instrument, modifier_name)

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


    def __instrument_new_variables(self, predicate, modifier_body, functions_to_instrument, instrument_for_echidna):
        new_modifier_body = modifier_body

        if predicate.operator == parser.PREVIOUSLY:
            if instrument_for_echidna:
                initialization_code = f'bool {predicate.solidity_vars[0]};'
                update_code = f'{predicate.solidity_vars[0]}={predicate.values[0].solidity_repr};'

                self.__insert_in_contract(initialization_code)
                self.__insert_at_functions_beginning(functions_to_instrument, update_code)
            else:
                initialization_code = f'bool {predicate.solidity_vars[0]}={predicate.values[0].solidity_repr};\n'
                new_modifier_body = initialization_code + modifier_body
        elif predicate.operator == parser.SINCE:
            q = predicate.solidity_vars[0]
            p_since_q = predicate.solidity_vars[1]
            q_repr = predicate.values[1].solidity_repr
            p_repr = predicate.values[0].solidity_repr
            initialization_code = f'bool {q}=false;\nbool {p_since_q}=true;'
            update_code = '''if({q}){{\n{p_since_q}={p_repr}&&{p_since_q};\n}}\n{q}={q_repr}||{q};\n'''\
                .format(q=q, p_since_q=p_since_q, q_repr=q_repr, p_repr=p_repr)

            self.__insert_in_contract(initialization_code)
            new_modifier_body = modifier_body + update_code

        for term in predicate.values:
            new_modifier_body = self.__instrument_new_variables(term, new_modifier_body, functions_to_instrument, instrument_for_echidna)

        return new_modifier_body


    def __get_functions_to_instrument(self, predicate):
        functions_to_instrument = set()

        for variable_name in predicate.related_vars:

            if self.__is_solidity_property(variable_name):
                functions_to_instrument.update(self.__filter_to_instrument(self.contract_info.functions))
            else:
                variable = self.contract_info.get_state_variable_from_name(variable_name)
                functions_writing_variable = self.contract_info.get_functions_writing_to_variable(variable)

                functions_to_instrument.update(self.__filter_to_instrument(functions_writing_variable))

                functions_to_instrument.update(list(self.__get_public_callers(functions_writing_variable)))

            if len(functions_to_instrument) == len(self.contract_info.functions_entry_points):
                break

        # The initial state also needs to be checked:
        constructor = self.contract_info.constructor
        if constructor not in functions_to_instrument:
            functions_to_instrument.add(constructor)

        # We can thought of all no-state-changing functions as equivalent:
        for func in self.contract_info.functions:
            if self.__should_be_instrumented(func) and not func in functions_to_instrument:
                functions_to_instrument.add(func)
                break

        return functions_to_instrument


    def __filter_to_instrument(self, functions):
        return list(filter(lambda func: self.__should_be_instrumented(func), functions))


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


    def __insert_as_modifier(self, functions, modifier_name):
        for func in functions:
            func_line_numbers = func.source_mapping['lines']
            first_line_number = func_line_numbers[0] - 1
            first_line = self.contract_lines[first_line_number]

            new_first_line = first_line.replace(' returns', ' ' + modifier_name + ' returns', 1)
            if len(new_first_line) == len(first_line):
                new_first_line = first_line.replace('{', ' ' + modifier_name + ' {', 1)

            self.contract_lines[first_line_number] = new_first_line