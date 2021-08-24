#!/usr/bin/env python3

################ lis.py: Scheme Interpreter in Python 3.10
## (c) Peter Norvig, 2010-18; See http://norvig.com/lispy.html
## Minor edits for Fluent Python, Second Edition (O'Reilly, 2021)
## by Luciano Ramalho, adding type hints and pattern matching.

################ imports and types
import math
import operator as op
from collections import ChainMap
from collections.abc import MutableMapping
from typing import Any, TypeAlias

from exceptions import (
    UnexpectedCloseParen, UnexpectedEndOfSource, UndefinedSymbol,
    InvalidSyntax, EvaluatorException,
)

Symbol: TypeAlias = str
Number: TypeAlias = int | float
Atom: TypeAlias = int | float | Symbol
Expression: TypeAlias = Atom | list

TCO_ENABLED = True


class Environment(ChainMap):
    "A ChainMap that allows updating an item in-place."

    def change(self, key: Symbol, value: object) -> None:
        "Find where key is defined and change the value there."
        for map in self.maps:
            if key in map:
                map[key] = value
                return
        raise KeyError(key)


class Procedure:
    "A user-defined Scheme procedure."

    def __init__(
        self, parms: list[Symbol], body: list[Expression], env: Environment
    ):
        self.parms = parms
        self.body = body
        self.definition_env = env

    def application_env(self, args: list[Expression]) -> Environment:
        local_env = dict(zip(self.parms, args))
        return Environment(local_env, self.definition_env)

    def __call__(self, *args: Expression) -> Any:
        env = self.application_env(args)
        for exp in self.body:
            result = evaluate(exp, env)
        return result


################ global environment


def standard_env() -> Environment:
    "An environment with some Scheme standard procedures."
    env = Environment()
    env.update(vars(math))   # sin, cos, sqrt, pi, ...
    env.update({
            '+': op.add,
            '-': op.sub,
            '*': op.mul,
            '/': op.truediv,
            '//': op.floordiv,
            '>': op.gt,
            '<': op.lt,
            '>=': op.ge,
            '<=': op.le,
            '=': op.eq,
            'abs': abs,
            'append': op.add,
            'apply': lambda proc, args: proc(*args),
            'begin': lambda *x: x[-1],
            'car': lambda x: x[0],
            'cdr': lambda x: x[1:],
            'cons': lambda x, y: [x] + y,
            'eq?': op.is_,
            'equal?': op.eq,
            'filter': lambda *args: list(filter(*args)),
            'length': len,
            'list': lambda *x: list(x),
            'list?': lambda x: isinstance(x, list),
            'map': lambda *args: list(map(*args)),
            'max': max,
            'min': min,
            'not': op.not_,
            'null?': lambda x: x == [],
            'number?': lambda x: isinstance(x, (int, float)),
            'procedure?': callable,
            'round': round,
            'symbol?': lambda x: isinstance(x, Symbol),
    })
    return env


################ parse, tokenize, and read_from_tokens


def parse(source: str) -> Expression:
    "Read a Scheme expression from a string."
    return read_from_tokens(tokenize(source))


def tokenize(s: str) -> list[str]:
    "Convert a string into a list of tokens."
    return s.replace('(', ' ( ').replace(')', ' ) ').split()


def read_from_tokens(tokens: list[str]) -> Expression:
    "Read an expression from a sequence of tokens."
    if len(tokens) == 0:
        raise UnexpectedEndOfSource()
    token = tokens.pop(0)
    if '(' == token:
        exp = []
        while tokens and tokens[0] != ')':
            exp.append(read_from_tokens(tokens))
        if not tokens:
            raise UnexpectedEndOfSource()
        tokens.pop(0)  # discard ')'
        return exp
    elif ')' == token:
        raise UnexpectedCloseParen()
    else:
        return parse_atom(token)


def parse_atom(token: str) -> Atom:
    "Numbers become numbers; every other token is a symbol."
    try:
        return int(token)
    except ValueError:
        try:
            return float(token)
        except ValueError:
            return Symbol(token)


################ interaction: a REPL


def repl(prompt: str = 'lis.py> ') -> None:
    "A prompt-read-evaluate-print loop."
    global_env: Environment = standard_env()
    while True:
        val = evaluate(parse(input(prompt)), global_env)
        if val is not None:
            print(lispstr(val))


def lispstr(exp: object) -> str:
    "Convert a Python object back into a Lisp-readable string."
    if isinstance(exp, list):
        return '(' + ' '.join(map(lispstr, exp)) + ')'
    else:
        return str(exp)


################ special forms

def cond_form(clauses: list[Expression], env: Environment) -> Any:
    "Special form: (cond (test exp)* (else eN)?)."
    for clause in clauses:
        match clause:
            case ['else', *body]:
                for exp in body:
                    result = evaluate(exp, env)
                return result
            case [test, *body] if evaluate(test, env):
                for exp in body:
                    result = evaluate(exp, env)
                return result


def or_form(expressions: list[Expression], env: Environment) -> Any:
    "Special form: (or exp*)"
    value = False
    for exp in expressions:
        value = evaluate(exp, env)
        if value:
            return value
    return value


def and_form(expressions: list[Expression], env: Environment) -> Any:
    "Special form: (and exp*)"
    value = True
    for exp in expressions:
        value = evaluate(exp, env)
        if not value:
            return value
    return value

################ eval

KEYWORDS_1 = ['quote', 'if', 'define', 'lambda']
KEYWORDS_2 = ['set!', 'cond', 'or', 'and', 'begin']
KEYWORDS = KEYWORDS_1 + KEYWORDS_2

# Special marks in syntax descriptions:
#   * : 0 or more
#   + : 1 or more
#   ? : 0 or 1

def evaluate(exp: Expression, env: Environment) -> Any:
    "Evaluate an expression in an environment."
    while True:
        match exp:
            case int(x) | float(x):                             # number literal
                return x
            case Symbol(var):                                   # variable reference
                try:
                    return env[var]
                except KeyError as exc:
                    raise UndefinedSymbol(var) from exc
            case ['quote' | "'", exp]:                                # (quote exp)
                return exp
            case ['if', test, consequence, alternative]:        # (if test consequence alternative)
                if evaluate(test, env):
                    exp = consequence
                else:
                    exp = alternative
            case ['define', Symbol(var), value_exp]:            # (define var exp)
                env[var] = evaluate(value_exp, env)
                return
            case ['set!', Symbol(var), value_exp]:              # (set! var exp)
                env.change(var, evaluate(value_exp, env))
                return
            case ['define', [Symbol(name), *parms], *body       # (define (name parm*)) body+)
                ] if len(body) > 0:
                env[name] = Procedure(parms, body, env)
                return
            case ['lambda', [*parms], *body] if len(body) > 0:  # (lambda (parm*) body+)
                return Procedure(parms, body, env)
            case ['cond', *clauses]:                            # (cond (t1 e1)* (else eN)?)
                return cond_form(clauses, env)
            case ['or', *expressions]:                          # (or exp*)
                return or_form(expressions, env)
            case ['and', *expressions]:                         # (and exp*)
                return and_form(expressions, env)
            case ['begin', *expressions]:                       # (begin exp+)
                for exp in expressions[:-1]:
                    evaluate(exp, env)
                exp = expressions[-1]
            case [op, *args] if op not in KEYWORDS:             # (proc exp*)
                proc = evaluate(op, env)
                values = [evaluate(arg, env) for arg in args]
                if TCO_ENABLED and isinstance(proc, Procedure):
                     exp = ['begin', *proc.body]
                     env = proc.application_env(values)
                else:
                    try:
                        return proc(*values)
                    except TypeError as exc:
                        msg = (f'{exc!r}\ninvoking: {proc!r}({args!r}):'
                               f'\nsource: {lispstr(exp)}\nAST: {exp!r}')
                        raise EvaluatorException(msg) from exc
            case _:
                raise InvalidSyntax(lispstr(exp))


if __name__ == '__main__':
    repl()
