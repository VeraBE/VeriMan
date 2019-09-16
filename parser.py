import tatsu
import re
import random, string
from tatsu.ast import AST
from iteration_utilities import deepflatten


TRUE = 'true'
FALSE = 'false'
AND = '&&'
OR = '||'
EQUAL = '=='
NOTEQUAL = '!='
NOT = '!'
SINCE = 'since'
PREVIOUSLY = 'previously'
ONCE = 'once'
ALWAYS = 'always'

GRAMMAR_FILE = 'grammar.txt'

VARIABLE_NAME_LENGTH = 8


class Parser:

    def __init__(self):
        with open(GRAMMAR_FILE, 'r') as grammar_file:
            self.grammar = tatsu.compile(grammar_file.read())


    def parse(self, text):
        predicate = self.grammar.parse(text, semantics=Semantics())

        if not isinstance(predicate, Predicate):
            predicate = Term(predicate)

        return predicate


    @staticmethod
    def create_variable_name(base):
        return 'VeriMan_' + base + '_' + ''.join(
            random.choice(string.ascii_lowercase) for _ in range(VARIABLE_NAME_LENGTH))


class Semantics(object):

    def expression(self, ast):
        if not isinstance(ast, AST):
            return ast
        elif ast.op in [AND, OR, EQUAL, NOTEQUAL]:
            return Predicate(ast.op, [ast.left, ast.right])
        else:
            raise Exception('Unknown operator', ast.op)


    def term(self, ast):
        if not isinstance(ast, AST):
            return ast
        elif ast.op == SINCE:
            return Predicate(ast.op, [ast.left, ast.right])
        elif ast.op == ONCE:
            return Predicate(SINCE, [TRUE, ast.value])
        elif ast.op == ALWAYS:
            return Predicate(NOT, [Predicate(SINCE, [TRUE, Predicate(NOT, [ast.value])])])
        elif ast.op in [PREVIOUSLY, NOT]:
            return Predicate(ast.op, [ast.value])
        else:
            raise Exception('Unknown operator', ast.op)


class Predicate:

    def __init__(self, operator, values):
        self.operator = operator
        self.values = []
        self.related_vars = []

        for value in values:
            term = value

            if not isinstance(value, Predicate):
                term = Term(value)

            self.related_vars += term.related_vars
            self.values.append(term)

        self.related_vars = list(set(self.related_vars))

        if operator == PREVIOUSLY:
            new_var = Parser.create_variable_name('prev')
            self.solidity_repr = new_var
            self.solidity_vars = [new_var]
        elif operator == SINCE:
            q = Parser.create_variable_name('q')
            p_since_q = Parser.create_variable_name('p_since_q')
            self.solidity_repr = f'({q} {OR} {p_since_q})'
            self.solidity_vars = [q, p_since_q]
        else:
            self.solidity_vars = []
            if self.operator in [AND, OR, EQUAL, NOTEQUAL]:
                self.solidity_repr = self.values[0].solidity_repr + " " + self.operator + " " + self.values[1].solidity_repr
            elif self.operator == NOT:
                self.solidity_repr = '!' + self.values[0].solidity_repr


class Term(Predicate):

    def __init__(self, value):
        super().__init__('', [])

        if isinstance(value, list):
            self.solidity_repr = ' '.join(list(deepflatten(value, types=list)))
        elif isinstance(value, str):
            self.solidity_repr = value
        else:
            raise Exception('Unexpected term')

        self.solidity_repr = '(' + self.solidity_repr.rstrip().lstrip() + ')'

        vars = re.findall('[a-zA-Z0-9_.]*?[a-zA-Z][a-zA-Z0-9_.]*', self.solidity_repr)
        # TODO improve:
        vars = list(filter(lambda elem: elem != TRUE and elem != FALSE, vars))
        self.related_vars = list(set(vars))
