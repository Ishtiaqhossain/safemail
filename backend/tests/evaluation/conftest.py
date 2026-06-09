import pytest


def pytest_addoption(parser):
    parser.addoption("--skip-live", action="store_true", default=False, help="Skip tests that call the Anthropic API")


def pytest_configure(config):
    config.addinivalue_line("markers", "live: marks test as requiring a real Anthropic API call")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--skip-live"):
        skip_live = pytest.mark.skip(reason="--skip-live passed")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip_live)
