def test_no_web_framework_dependency() -> None:
    content = open("pyproject.toml").read()
    assert "fastapi" not in content.lower()
