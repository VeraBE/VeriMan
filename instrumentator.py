from slither.slither import Slither
from parser import Parser


class Instrumentator:

    def __init__(self):
        self.contract_path = ''
        self.contract_name = ''
        self.contract_lines = []


    def instrument(self, contract_path, contract_name, predicates):
        self.contract_path = contract_path
        self.contract_name = contract_name

        with open(self.contract_path) as contract_file:
            contract = contract_file.read()
        contract = contract.replace('}', '\n}')
        self.contract_lines = contract.split('\n')

        parser = Parser()

        for predicate_string in predicates:
            predicate = parser.parse(predicate_string)

            # TODO "missing" constructor needs to be considered

            self.instrument_new_variables(predicate)

            self.instrument_assert(predicate)

        contract = '\n'.join(self.contract_lines)
        with open(self.contract_path, 'w') as contract_file:
            contract_file.write(contract)


    def instrument_new_variables(self, predicate):
        if len(predicate.solidity_vars) > 0:
            related_functions = self.get_related_functions(predicate)
            if predicate.operator == "previously":
                # FIXME related
                self.insert_in_functions(related_functions, predicate.initialization_code, self.insert_at_beginning_of_functions)
            elif predicate.operator == "since":
                self.insert_contract_variables(predicate.initialization_code)
                self.insert_in_functions(related_functions, predicate.update_code, self.insert_at_end_of_functions)
            else:
                raise Exception('Unexpected predicate')

        for term in predicate.values:
            self.instrument_new_variables(term)


    def instrument_assert(self, predicate):
        related_functions = self.get_related_functions(predicate)
        assert_string = 'assert(' + predicate.solidity_repr + ');'

        self.insert_in_functions(related_functions, assert_string, self.insert_at_end_of_functions)


    def get_related_functions(self, predicate):
        related_functions = set()

        slither = Slither(self.contract_path)
        main_contract = slither.get_contract_from_name(self.contract_name)

        for variable_name in predicate.related_vars:
            variable = main_contract.get_state_variable_from_name(variable_name)
            if variable != None:  # TODO improve
                functions_writing_variable = main_contract.get_functions_writing_to_variable(variable)
                related_functions = related_functions.union(self.get_public_callers(functions_writing_variable))

        return related_functions


    def get_public_callers(self, functions):
        result = set()

        for func in functions:
            if func.visibility == 'public':
                result.add(func.name)
            else:
                # TODO check for cycles?
                result = result.union(self.get_public_callers(func.reachable_from_functions))

        return result


    def insert_in_functions(self, function_names, code_string, insert_in_function):
        in_function = False
        open_blocks = 0
        for index, line in enumerate(self.contract_lines):
            # TODO check the line begins with spaces plus this:
            if "function " in line:
                found = False
                for function_name in function_names:
                    if "function " + function_name in line:
                        found = True
                        break
                in_function = found

            if in_function:
                self.contract_lines = insert_in_function(self.contract_lines, code_string, line, index, open_blocks)
                open_blocks = open_blocks + line.count("{") - line.count("}")


    def insert_contract_variables(self, initialization_string):
        in_contract = False
        for index, line in enumerate(self.contract_lines):
            in_contract = in_contract or "contract " in line
            if (in_contract and "{" in line) or (in_contract and "{" in line):
                self.contract_lines[index] = line.replace('{', '{\n' + initialization_string)
                break


    def insert_at_end_of_functions(self, contract_lines, code_string, line, index, open_blocks): # FIXME parameters
        if "return " in line:
            # TODO consider return might call another function:
            contract_lines[index] = line.replace('return ', code_string + '\nreturn ')

        open_blocks = open_blocks + line.count("{") - line.count("}")
        if open_blocks == 0:
            contract_lines[index] = line.replace('}', code_string + '\n}')

        return contract_lines


    def insert_at_beginning_of_functions(self, contract_lines, code_string, line, index, open_blocks):
        if ("function " in line and "{" in line) or (open_blocks == 0 and "{" in line):
            contract_lines[index] = line.replace('{', '{\n' + code_string)

        return contract_lines