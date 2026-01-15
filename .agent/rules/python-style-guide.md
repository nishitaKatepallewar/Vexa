---
trigger: manual
---

# Python Style Guide Summary

## 1. Critical Language Rules

### Linting & Imports

* **Linting:** Run `pylint` over your code. Suppress false positives locally using comments (e.g., `# pylint: disable=invalid-name`) rather than globally.
* **Imports:**
* Use `import x` for packages/modules.
* Use `from x import y` where `y` is a module.
* **Do not** use relative imports. Use the full package name.
* **Do not** use `import *`.



### Logic & Control Flow

* **Exceptions:**
* Use built-in exceptions (`ValueError`, etc.) when possible.
* Do not use `assert` for critical application logic.
* Minimize the code inside `try`/`except` blocks.


* **Mutable Global State:** Avoid it. Use module-level constants (read-only) instead.
* **Comprehensions:** Allowed for simple cases. If it requires complicated logic or multiple loops, use a standard loop instead.
* **True/False Evaluations:**
* Use "implicit" false (`if foo:` rather than `if len(foo) > 0:`).
* **Exception:** Always use `if foo is None:` to check for None. Never use `== None` or implicit boolean checks for None (since `0` or `[]` are also false).


* **Lambda:** One-liners only. If it's longer, define a function.

### Functions & Arguments

* **Default Arguments:** **NEVER** use mutable objects as default values.
* *Bad:* `def foo(a, b=[])`
* *Good:* `def foo(a, b=None): if b is None: b = []`


* **Properties:** Use `@property` for trivial data access logic. For complex logic, use explicit getter/setter methods.
* **Decorators:** Avoid `staticmethod`. Use `classmethod` only for constructors or global state modification.

### Files & Resources

* **Context Managers:** Always use `with open(...)` for files, sockets, and threaded locks to ensure they are closed properly.

---

## 2. Style & Formatting Rules

### Layout

* **Line Length:** Maximum **80 characters**.
* **Exception:** Long import statements and URLs in comments.
* **Continuation:** Use parentheses `()` for line continuation. **Do not** use backslashes `\`.


* **Indentation:** Use **4 spaces**. Never use tabs.
* **Blank Lines:**
* **2 lines** between top-level definitions (classes/functions).
* **1 line** between methods inside a class.


* **Whitespace:**
* No whitespace inside parentheses/brackets: `spam(1)` not `spam( 1 )`.
* No trailing whitespace at the end of lines.
* Surround binary operators with spaces: `x = 1` not `x=1`.



### Strings

* **Formatting:** Use f-strings (`f'{name}'`), `%` operator, or `.format()`.
* **Concatenation:** Do not use `+` to accumulate strings in a loop (it is slow). Use `''.join(list_of_strings)`.
* **Quotes:** Be consistent. Use `"""` for docstrings.

### Docstrings & Comments

* **Docstrings:** Mandatory for public modules, classes, and functions.
* Format: `"""Summary line.\n\nDescription..."""`
* Use sections: `Args:`, `Returns:` (or `Yields:`), and `Raises:`.


* **Comments:** Use `#` for block/inline comments. Ensure complete sentences and proper capitalization.
* **TODOs:** Format as `# TODO: link_to_issue - Explanation`.

### Main

* Always check if the file is being executed directly:
```python
def main():
    ...

if __name__ == '__main__':
    main()

```



---

## 3. Naming Conventions

Names should be descriptive and avoid abbreviations.

| Type | Convention | Example |
| --- | --- | --- |
| **Module** | `lower_with_under` | `my_module.py` |
| **Class** | `CapWords` | `MyClass` |
| **Function/Method** | `lower_with_under` | `my_function()` |
| **Variable** | `lower_with_under` | `my_variable` |
| **Constant** | `CAPS_WITH_UNDER` | `MAX_RETRIES` |
| **Protected Instance** | `_lower_with_under` | `_internal_variable` |
| **Private (Double)** | Not recommended | Avoid `__double_under` |

---

## 4. Type Annotations

Strongly encouraged for public APIs.

* **Syntax:**
```python
def my_func(a: int, b: str | None = None) -> list[int]:
    ...

```


* **Generics:** Use `Sequence`, `Mapping` from `collections.abc` rather than concrete `list` or `dict` for arguments.
* **None:** If an argument can be None, it must be typed as `Type | None` (or `Optional[Type]`).