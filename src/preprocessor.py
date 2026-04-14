import sys
from pycparser import parse_file, c_generator
from pycparser.c_ast import FileAST
from loop_bounds import add_loop_bounds


def preprocess_file(file_path: str) -> str:
    """Preprocesses the input file using the pycparser library"""
    ast = parse_file(file_path)
    ast = constrain_structured_arguments(ast)
    ast = constrain_gpio_reads(ast)
    ast = add_loop_bounds(ast)

    find_risky_functions(ast)

    # Convert the final AST back into C code.
    generator = c_generator.CGenerator()
    c_code = generator.visit(ast)
    print(c_code)


def constrain_structured_arguments(ast: FileAST) -> FileAST:
    ...
    return ast


def constrain_gpio_reads(ast: FileAST) -> FileAST:
    ...
    return ast


def find_risky_functions(ast: FileAST):
    ...
    # Create risky JSON
