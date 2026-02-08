import ast
import os


class AwaitFinder(ast.NodeVisitor):
    def __init__(self):
        self.found_await = False

    def visit_Await(self, node):
        self.found_await = True

    def visit_AsyncFor(self, node):
        self.found_await = True

    def visit_AsyncWith(self, node):
        self.found_await = True

    # Do not visit nested AsyncFunctionDef or FunctionDef
    # We want to check if the CURRENT function has await, not its children.
    # The children will be visited by the main AsyncVisitor when it walks the tree.
    def visit_AsyncFunctionDef(self, node):
        pass

    def visit_FunctionDef(self, node):
        pass


class AsyncVisitor(ast.NodeVisitor):
    def __init__(self, filepath):
        self.issues = []
        self.filepath = filepath

    def visit_AsyncFunctionDef(self, node):
        # We need to scan the body of THIS function for await.
        finder = AwaitFinder()
        for child in node.body:
            finder.visit(child)

        if not finder.found_await:
            # Check for @abstractmethod
            is_abstract = False
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Name) and decorator.id == "abstractmethod":
                    is_abstract = True
                elif (
                    isinstance(decorator, ast.Attribute)
                    and decorator.attr == "abstractmethod"
                ):
                    is_abstract = True

            # Check if empty (pass/docstring only)
            if not is_abstract:
                is_empty_or_doc_only = True
                for stmt in node.body:
                    if isinstance(stmt, ast.Pass):
                        continue
                    if isinstance(stmt, ast.Expr) and isinstance(
                        stmt.value, (ast.Constant, ast.Str)
                    ):
                        continue
                    is_empty_or_doc_only = False
                    break

                if not is_empty_or_doc_only:
                    self.issues.append(
                        f"{self.filepath}:{node.lineno} Function '{node.name}' is async but has no await."
                    )

        # Continue visiting to find nested functions
        self.generic_visit(node)


def check_file(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        tree = ast.parse(content)
        visitor = AsyncVisitor(filepath)
        visitor.visit(tree)
        for issue in visitor.issues:
            print(f"ISSUE: {issue}")
    except (SyntaxError, UnicodeDecodeError):
        # Ignore errors (e.g. syntax errors in template files)
        pass


if __name__ == "__main__":
    import sys

    base_dir = sys.argv[1] if len(sys.argv) > 1 else "/home/ubuntu/venom"
    print(f"Scanning all .py files in {base_dir}...")

    count = 0
    for root, dirs, files in os.walk(base_dir):
        # Skip hidden directories and virtualenvs
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "venv"]

        for file in files:
            if file.endswith(".py"):
                full_path = os.path.join(root, file)
                check_file(full_path)
                count += 1

    print(f"Scanned {count} files.")
