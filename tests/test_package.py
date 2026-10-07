import tensdireito_content_engine


def test_package_imports_and_exposes_version():
    assert isinstance(tensdireito_content_engine.__version__, str)
    assert tensdireito_content_engine.__version__
