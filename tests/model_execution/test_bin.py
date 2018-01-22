import glob
import tarfile
from tempfile import NamedTemporaryFile

from chainmap import ChainMap
from itertools import chain
from backports.tempfile import TemporaryDirectory
from unittest import TestCase

import os

from copy import deepcopy
from hypothesis import given
from hypothesis.strategies import sampled_from, lists
from mock import patch
from pathlib2 import Path

from oasislmf.model_execution.bin import create_binary_files, INPUT_FILES, create_binary_tar_file, TAR_FILE, \
    check_conversion_tools, check_inputs_directory, GUL_INPUT_FILES, OPTIONAL_INPUT_FILES, IL_INPUT_FILES, \
    prepare_model_run_directory
from oasislmf.utils.exceptions import OasisException

ECHO_CONVERSION_INPUT_FILES = {k: ChainMap({'conversion_tool': 'echo'}, v) for k, v in INPUT_FILES.items()}


def standard_input_files(min_size=0):
    return lists(
        sampled_from([target['name'] for target in chain(GUL_INPUT_FILES, OPTIONAL_INPUT_FILES)]),
        min_size=min_size,
        unique=True,
    )


def il_input_files(min_size=0):
    return lists(
        sampled_from([target['name'] for target in IL_INPUT_FILES]),
        min_size=min_size,
        unique=True,
    )


def tar_file_targets(min_size=0):
    return lists(
        sampled_from([target['name'] + '.bin' for target in INPUT_FILES.values()]),
        min_size=min_size,
        unique=True,
    )


class CreateBinaryFiles(TestCase):
    def test_directory_only_contains_excluded_files___tar_is_empty(self):
        with TemporaryDirectory() as csv_dir, TemporaryDirectory() as bin_dir:
            with open(os.path.join(csv_dir, 'another_file'), 'w') as f:
                f.write('file data')

            create_binary_files(csv_dir, bin_dir)

            self.assertEqual(0, len(glob.glob(os.path.join(csv_dir, '*.bin'))))

    @given(standard_input_files(min_size=1), il_input_files(min_size=1))
    def test_contains_il_and_standard_files_but_do_il_is_false___il_files_are_excluded(self, standard, il):
        with patch('oasislmf.model_execution.bin.INPUT_FILES', ECHO_CONVERSION_INPUT_FILES), TemporaryDirectory() as csv_dir, TemporaryDirectory() as bin_dir:
            for target in chain(standard, il):
                with open(os.path.join(csv_dir, target + '.csv'), 'w') as f:
                    f.write(target)

            create_binary_files(csv_dir, bin_dir, do_il=False)

            self.assertEqual(len(standard), len(glob.glob(os.path.join(bin_dir, '*.bin'))))
            for filename in (f + '.bin' for f in standard):
                self.assertTrue(os.path.exists(os.path.join(bin_dir, filename)))

    @given(standard_input_files(min_size=1), il_input_files(min_size=1))
    def test_contains_il_and_standard_files_but_do_il_is_true___all_files_are_included(self, standard, il):
        with patch('oasislmf.model_execution.bin.INPUT_FILES', ECHO_CONVERSION_INPUT_FILES), TemporaryDirectory() as csv_dir, TemporaryDirectory() as bin_dir:
            for target in chain(standard, il):
                with open(os.path.join(csv_dir, target + '.csv'), 'w') as f:
                    f.write(target)

            create_binary_files(csv_dir, bin_dir, do_il=True)

            self.assertEqual(len(standard) + len(il), len(glob.glob(os.path.join(bin_dir, '*.bin'))))
            for filename in (f + '.bin' for f in chain(standard, il)):
                self.assertTrue(os.path.exists(os.path.join(bin_dir, filename)))


class CreateBinaryTarFile(TestCase):
    def test_directory_only_contains_excluded_files___tar_is_empty(self):
        with TemporaryDirectory() as d:
            with open(os.path.join(d, 'another_file'), 'w') as f:
                f.write('file data')

            create_binary_tar_file(d)

            with tarfile.open(os.path.join(d, TAR_FILE), 'r:gz') as tar:
                self.assertEqual(0, len(tar.getnames()))

    @given(tar_file_targets(min_size=1))
    def test_directory_contains_some_target_files___target_files_are_included(self, targets):
        with TemporaryDirectory() as d:
            for target in targets:
                with open(os.path.join(d, target), 'w') as f:
                    f.write(target)

            create_binary_tar_file(d)

            with tarfile.open(os.path.join(d, TAR_FILE), 'r:gz') as tar:
                self.assertEqual(len(targets), len(tar.getnames()))
                self.assertEqual(set(targets), set(tar.getnames()))


class CheckConversionTools(TestCase):
    def test_conversion_tools_all_exist___result_is_true(self):
        existing_conversions = deepcopy(INPUT_FILES)
        for value in existing_conversions.values():
            value['conversion_tool'] = 'python'

        with patch('oasislmf.model_execution.bin.INPUT_FILES', existing_conversions):
            self.assertTrue(check_conversion_tools())

    def test_some_conversion_tools_are_missing___error_is_raised(self):
        missing_conversions = deepcopy(INPUT_FILES)
        for value in missing_conversions.values():
            value['conversion_tool'] = 'missing_executable'

        with patch('oasislmf.model_execution.bin.INPUT_FILES', missing_conversions):
            with self.assertRaises(OasisException):
                check_conversion_tools()


class CheckInputDirectory(TestCase):
    def test_tar_file_already_exists___exception_is_raised(self):
        with TemporaryDirectory() as d:
            Path(os.path.join(d, TAR_FILE)).touch()
            with self.assertRaises(OasisException):
                check_inputs_directory(d, False)

    @given(il_input_files())
    def test_do_il_is_false_non_il_input_files_are_missing__exception_is_raised(self, il_files):
        with TemporaryDirectory() as d:
            for p in il_files:
                Path(os.path.join(d, p + '.csv')).touch()

            with self.assertRaises(OasisException):
                check_inputs_directory(d, False)

    def test_do_is_is_false_non_il_input_files_are_present___no_exception_is_raised(self):
        with TemporaryDirectory() as d:
            for input_file in GUL_INPUT_FILES:
                Path(os.path.join(d, input_file['name'] + '.csv')).touch()

            try:
                check_inputs_directory(d, False)
            except Exception as e:
                self.fail('Exception was raised {}: {}'.format(type(e), e))

    def test_do_il_is_true_all_input_files_are_missing__exception_is_raised(self):
        with TemporaryDirectory() as d:
            with self.assertRaises(OasisException):
                check_inputs_directory(d, True)

    def test_do_il_is_true_gul_input_files_are_missing__exception_is_raised(self):
        with TemporaryDirectory() as d:
            for p in IL_INPUT_FILES:
                Path(os.path.join(d, p['name'] + '.csv')).touch()

            with self.assertRaises(OasisException):
                check_inputs_directory(d, True)

    def test_do_il_is_true_il_input_files_are_missing__exception_is_raised(self):
        with TemporaryDirectory() as d:
            for p in GUL_INPUT_FILES:
                Path(os.path.join(d, p['name'] + '.csv')).touch()

            with self.assertRaises(OasisException):
                check_inputs_directory(d, True)

    def test_do_il_is_true_all_input_files_are_present___no_exception_is_raised(self):
        with TemporaryDirectory() as d:
            for p in chain(GUL_INPUT_FILES, IL_INPUT_FILES):
                Path(os.path.join(d, p['name'] + '.csv')).touch()

            try:
                check_inputs_directory(d, True)
            except Exception as e:
                self.fail('Exception was raised {}: {}'.format(type(e), e))

    def test_do_il_is_false_il_bin_files_are_present___no_exception_is_raised(self):
        with TemporaryDirectory() as d:
            for p in chain(GUL_INPUT_FILES, IL_INPUT_FILES):
                Path(os.path.join(d, p['name'] + '.csv')).touch()

            for p in IL_INPUT_FILES:
                Path(os.path.join(d, p['name'] + '.bin')).touch()

            try:
                check_inputs_directory(d, False)
            except Exception as e:
                self.fail('Exception was raised {}: {}'.format(type(e), e))

    def test_do_il_is_false_gul_bin_files_are_present___exception_is_raised(self):
        with TemporaryDirectory() as d:
            for p in chain(GUL_INPUT_FILES, IL_INPUT_FILES):
                Path(os.path.join(d, p['name'] + '.csv')).touch()

            for p in GUL_INPUT_FILES:
                Path(os.path.join(d, p['name'] + '.bin')).touch()

            with self.assertRaises(OasisException):
                check_inputs_directory(d, False)

    def test_do_il_is_true_gul_bin_files_are_present___exception_is_raised(self):
        with TemporaryDirectory() as d:
            for p in chain(GUL_INPUT_FILES, IL_INPUT_FILES):
                Path(os.path.join(d, p['name'] + '.csv')).touch()

            for p in GUL_INPUT_FILES:
                Path(os.path.join(d, p['name'] + '.bin')).touch()

            with self.assertRaises(OasisException):
                check_inputs_directory(d, True)

    def test_do_il_is_true_il_bin_files_are_present___exception_is_raised(self):
        with TemporaryDirectory() as d:
            for p in chain(GUL_INPUT_FILES, IL_INPUT_FILES):
                Path(os.path.join(d, p['name'] + '.csv')).touch()

            for p in IL_INPUT_FILES:
                Path(os.path.join(d, p['name'] + '.bin')).touch()

            with self.assertRaises(OasisException):
                check_inputs_directory(d, True)

    def test_do_il_is_true_no_bin_files_are_present___no_exception_is_raised(self):
        with TemporaryDirectory() as d:
            for p in chain(GUL_INPUT_FILES, IL_INPUT_FILES):
                Path(os.path.join(d, p['name'] + '.csv')).touch()

            for p in IL_INPUT_FILES:
                Path(os.path.join(d, p['name'] + '.bin')).touch()

            try:
                check_inputs_directory(d, False)
            except Exception as e:
                self.fail('Exception was raised {}: {}'.format(type(e), e))


class PrepareModelRunDirectory(TestCase):
    def test_directory_is_empty___child_directories_are_created(self):
        with TemporaryDirectory() as d:
            prepare_model_run_directory(d)

            self.assertTrue(os.path.exists(os.path.join(d, 'fifo')))
            self.assertTrue(os.path.exists(os.path.join(d, 'input')))
            self.assertTrue(os.path.exists(os.path.join(d, 'input', 'csv')))
            self.assertTrue(os.path.exists(os.path.join(d, 'output')))
            self.assertTrue(os.path.exists(os.path.join(d, 'static')))
            self.assertTrue(os.path.exists(os.path.join(d, 'work')))

    def test_input_directory_is_supplied___input_files_are_copied_to_input_csv(self):
        with TemporaryDirectory() as output_path, TemporaryDirectory() as input_path:
            Path(os.path.join(input_path, 'a_file.csv')).touch()

            prepare_model_run_directory(output_path, oasis_files_src_path=input_path)

            self.assertTrue(os.path.exists(os.path.join(output_path, 'input', 'csv', 'a_file.csv')))

    def test_settings_file_is_supplied___settings_file_is_copied_into_run_dir(self):
        with TemporaryDirectory() as output_path, NamedTemporaryFile('w') as input_file:
            input_file.write('conf stuff')
            input_file.flush()

            prepare_model_run_directory(output_path, analysis_settings_json_src_file_path=input_file.name)

            with open(os.path.join(output_path, 'analysis_settings.json')) as output_conf:
                self.assertEqual('conf stuff', output_conf.read())

    def test_model_data_src_is_supplied___symlink_to_output_dir_static_is_created(self):
        with TemporaryDirectory() as output_path, TemporaryDirectory() as input_path:
            Path(os.path.join(input_path, 'linked_file')).touch()

            prepare_model_run_directory(output_path, model_data_src_path=input_path)

            self.assertTrue(os.path.exists(os.path.join(output_path, 'static', 'linked_file')))
