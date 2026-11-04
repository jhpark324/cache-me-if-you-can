import pytest

from second_brain.brand import DEFAULT_PORT
from second_brain.config import Settings


def test_dedicated_port_is_default_for_explicit_and_environment_settings(tmp_path, monkeypatch):
    monkeypatch.setenv('SECOND_BRAIN_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('SECOND_BRAIN_PORT', raising=False)

    assert DEFAULT_PORT == 52761
    assert Settings(tmp_path).origin == 'http://127.0.0.1:52761'
    assert Settings.load().origin == Settings(tmp_path).origin
    assert not tmp_path.joinpath('local-access.json').exists()


@pytest.mark.parametrize('port', [1, 8000, 53127, 65535])
def test_custom_port_controls_origin(tmp_path, monkeypatch, port):
    monkeypatch.setenv('SECOND_BRAIN_PORT', str(port))

    assert Settings(tmp_path, port=port).origin == f'http://127.0.0.1:{port}'
    assert Settings.load().port == port


def test_environment_port_normalizes_surrounding_whitespace_and_leading_zeroes(monkeypatch):
    monkeypatch.setenv('SECOND_BRAIN_PORT', ' 0008000 ')

    assert Settings.load().origin == 'http://127.0.0.1:8000'


@pytest.mark.parametrize('environment_port', ['8000', 'not-a-port', '0', '65536'])
def test_explicit_loaded_port_takes_precedence_over_environment(monkeypatch, environment_port):
    monkeypatch.setenv('SECOND_BRAIN_PORT', environment_port)

    assert Settings.load(port=53127).origin == 'http://127.0.0.1:53127'


@pytest.mark.parametrize('port', [0, -1, 65536, True, 52761.0, '52761'])
def test_explicit_loaded_port_is_validated_without_environment_fallback(monkeypatch, port):
    monkeypatch.setenv('SECOND_BRAIN_PORT', '52761')

    with pytest.raises(ValueError, match='integer between 1 and 65535'):
        Settings.load(port=port)


def test_explicit_loaded_data_directory_takes_precedence_without_initialization(tmp_path, monkeypatch):
    environment_data = tmp_path / 'environment-store'
    explicit_data = tmp_path / 'selected-store'
    monkeypatch.setenv('SECOND_BRAIN_DATA_DIR', str(environment_data))
    monkeypatch.setenv('SECOND_BRAIN_PORT', '53127')

    settings = Settings.load(data_dir=explicit_data)

    assert settings.data_dir == explicit_data
    assert settings.port == 53127
    assert not explicit_data.exists()
    assert not environment_data.exists()


@pytest.mark.parametrize('port', [0, -1, 65536, True, 52761.0, '52761', None])
def test_invalid_explicit_port_is_rejected_before_initialization(tmp_path, port):
    data_dir = tmp_path / 'not-created'

    with pytest.raises(ValueError, match='integer between 1 and 65535'):
        Settings(data_dir, port=port)
    assert not data_dir.exists()


@pytest.mark.parametrize('port', ['', '0', '-1', '65536', '655350', '1.5', '1e3', '52_761', '+8000', 'secret-value'])
def test_invalid_environment_port_is_rejected_without_echoing_input(tmp_path, monkeypatch, port):
    data_dir = tmp_path / 'not-created'
    monkeypatch.setenv('SECOND_BRAIN_DATA_DIR', str(data_dir))
    monkeypatch.setenv('SECOND_BRAIN_PORT', port)

    with pytest.raises(ValueError) as error:
        Settings.load()
    assert str(error.value) == 'SECOND_BRAIN_PORT must be an integer between 1 and 65535.'
    assert not data_dir.exists()
