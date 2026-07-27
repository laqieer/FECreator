# Task 1 Report

## RED: `pytest -q tests/test_release_tag.py` (before fix)

```text
..F...........                                                           [100%]
================================== FAILURES ===================================
_________ test_main_returns_generic_error_for_malformed_package_init __________

tmp_path = WindowsPath('C:/Users/zhiwenzhu/AppData/Local/Temp/pytest-of-zhiwenzhu/pytest-842/test_main_returns_generic_erro0')
capsys = <_pytest.capture.CaptureFixture object at 0x000001B1D5842D90>

    def test_main_returns_generic_error_for_malformed_package_init(
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        pyproject = tmp_path / "pyproject.toml"
        package_init = tmp_path / "__init__.py"
        pyproject.write_text('[project]\nname = "fecreator"\nversion = "0.1.0"\n', encoding="utf-8")
        package_init.write_text('__version__ = "0.1.0"\n(', encoding="utf-8")

>       rc = main(["--tag", "v0.1.0", "--pyproject", str(pyproject), "--package-init", str(package_init)])
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests\test_release_tag.py:44:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
scripts\validate_release_tag.py:68: in main
    print(validate_release_tag(args.tag, args.pyproject, args.package_init))
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
scripts\validate_release_tag.py:52: in validate_release_tag
    if version != _read_package_version(package_init):
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
scripts\validate_release_tag.py:29: in _read_package_version
    tree = ast.parse(package_init.read_text(encoding="utf-8"))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

source = '__version__ = "0.1.0"\n(', filename = '<unknown>', mode = 'exec'
type_comments = False, feature_version = -1

    def parse(source, filename='<unknown>', mode='exec', *,
              type_comments=False, feature_version=None):
        """
        Parse the source into an AST node.
        Equivalent to compile(source, filename, mode, PyCF_ONLY_AST).
        Pass type_comments=True to get back type comments where the syntax allows.
        """
        flags = PyCF_ONLY_AST
        if type_comments:
            flags |= PyCF_TYPE_COMMENTS
        if isinstance(feature_version, tuple):
            major, minor = feature_version  # Should be a 2-tuple.
            assert major == 3
            feature_version = minor
        elif feature_version is None:
            feature_version = -1
        # Else it should be an int giving the minor version for 3.x.
>       return compile(source, filename, mode, flags,
                       _feature_version=feature_version)
E         File "<unknown>", line 2
E           (
E           ^
E       SyntaxError: '(' was never closed

C:\Users\zhiwenzhu\AppData\Local\Programs\Python\Python311\Lib\ast.py:50: SyntaxError
=========================== short test summary info ===========================
FAILED tests/test_release_tag.py::test_main_returns_generic_error_for_malformed_package_init
```

## GREEN: `pytest -q tests/test_release_tag.py` (after fix)

```text
..............                                                           [100%]
```

## Verification: `pytest -q`

```text
........................................................................ [  7%]
........................................................................ [ 14%]
........................................................................ [ 21%]
........................................................................ [ 29%]
........................................................................ [ 36%]
........................................................s............... [ 43%]
....................................................s................... [ 51%]
........................................................................ [ 58%]
........................................................................ [ 65%]
........................................................................ [ 72%]
........................................................................ [ 80%]
........................................................................ [ 87%]
........................................................................ [ 94%]
...................................................                      [100%]
============================== warnings summary ===============================
..\..\..\..\Users\zhiwenzhu\AppData\Local\Programs\Python\Python311\Lib\site-packages\fastapi\testclient.py:1
  C:\Users\zhiwenzhu\AppData\Local\Programs\Python\Python311\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
```

## Verification: `ruff check .`

```text
All checks passed!
```

## Verification: `ruff format --check .`

```text
184 files already formatted
```

## Verification: `mypy src`

```text
Success: no issues found in 89 source files
```

## Verification: CLI smoke

```text
0.1.0
```
