def test_package_imports_and_has_version():
    import delivery_gate
    assert delivery_gate.__version__ == "0.1.0"
