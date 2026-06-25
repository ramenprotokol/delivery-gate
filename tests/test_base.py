def test_package_imports_and_has_version():
    import delivery_gate

    assert delivery_gate.__version__ == "0.1.0"


def test_result_and_enums_exist():
    from delivery_gate.base import Kind, Result, Status

    r = Result(check_id="x", label="X", status=Status.PASS, kind=Kind.AUTO, message="ok")
    assert r.status is Status.PASS
    assert r.kind is Kind.AUTO
    assert r.message == "ok"


def test_check_base_requires_run():
    import pytest

    from delivery_gate.base import Check

    with pytest.raises(NotImplementedError):
        Check().run(context=None)
