import pytest

from gusnet.inpfile_reader import InpFileReadError, read_inp_file


def test_reads_without_errors(test_inp_dir):
    inp_path = test_inp_dir / "single_pipe_warning.inp"
    sections, network, options = read_inp_file(inp_path)

    assert sections
    assert network
    assert options


def test_errors_on_options_value_error(test_inp_dir):
    bad_inp = test_inp_dir / "bad_syntax.inp"
    with pytest.raises(InpFileReadError, match="NOT-A-HEADLOSS"):
        read_inp_file(bad_inp)


def test_errors_on_wrong_length(test_inp_dir):
    bad_inp = test_inp_dir / "bad_syntax non existant pattern.inp"
    with pytest.raises(InpFileReadError, match="PATTERN_DOESNT_EXIST"):
        read_inp_file(bad_inp)


def test_error_on_non_existant_file(test_inp_dir):
    bad_inp = test_inp_dir / "this file does not exist.inp"

    with pytest.raises(InpFileReadError, match="this file does not exist"):
        read_inp_file(bad_inp)
