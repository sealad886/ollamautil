import unittest
import os
import shutil
from unittest.mock import patch
from src.ollamautil import ollamautil as ollamautil_module # Import the specific module

class TestOllamaUtil(unittest.TestCase):

    def setUp(self):
        self.temp_dir = 'temp_test_dir'
        os.makedirs(self.temp_dir, exist_ok=True)
        open(os.path.join(self.temp_dir, 'file1.txt'), 'a').close()
        os.makedirs(os.path.join(self.temp_dir, 'subdir'), exist_ok=True)
        open(os.path.join(self.temp_dir, 'subdir', 'file2.txt'), 'a').close()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_walk_dir(self): # Removed mock_ignore argument
        # Patch FILE_LIST_IGNORE using patch.object within the test
        with patch.object(ollamautil_module, 'FILE_LIST_IGNORE', ['.DS_Store']):
            expected_files = sorted([ # Ensure sorted order matches function output
                os.path.join(self.temp_dir, 'file1.txt'),
                os.path.join(self.temp_dir, 'subdir', 'file2.txt')
            ])
            # Create an ignored file to test the filter
            open(os.path.join(self.temp_dir, '.DS_Store'), 'a').close()
            actual_files = ollamautil_module.walk_dir(self.temp_dir)
            self.assertEqual(actual_files, expected_files)

    def test_get_models_table(self):
        # Use path-like names as expected by the function
        combined = [
            [f'library{os.sep}model1', ['tag1', 'tag2'], ['tag2', 'tag3']],
            [f'user{os.sep}model2', ['tag4'], ['tag5']]
        ]
        table = ollamautil_module.get_models_table(combined)
        self.assertIsNotNone(table)
        self.assertEqual(table.title, "Ollama GPTs Installed")
        self.assertEqual(len(table.rows), 5)  # 3 rows for model1 and 2 rows for model2
        self.assertEqual(table.field_names, ['No.', 'Lib', 'Model', 'Tag', 'External', 'Internal'])

    def test_build_ext_int_comb_filelist(self): # Removed mock arguments
        # Use patch.object context managers instead of decorators
        with patch.object(ollamautil_module, 'ollama_ext_dir', 'mock/external/ollama'), \
             patch.object(ollamautil_module, 'ollama_int_dir', 'mock/internal/ollama'), \
             patch.object(ollamautil_module, 'walk_dir') as mock_walk_dir:
            # Define what walk_dir should return for external and internal paths
            mock_walk_dir.side_effect = lambda path: {
                'mock/external/ollama/manifests': [
                   f'mock/external/ollama/manifests/manifests/library/modelA/tag1', # Added 'manifests'
                   f'mock/external/ollama/manifests/manifests/library/modelA/tag2', # Added 'manifests'
                   f'mock/external/ollama/manifests/manifests/user/modelB/latest'  # Added 'manifests'
               ],
               'mock/internal/ollama/manifests': [
                   f'mock/internal/ollama/manifests/manifests/library/modelA/tag2', # Added 'manifests'
                   f'mock/internal/ollama/manifests/manifests/custom/modelC/v1'   # Added 'manifests'
               ]
            }.get(path, [])  # Return empty list if path not matched

            external_dict, internal_dict, combined = ollamautil_module.build_ext_int_comb_filelist()

            print(f"external_dict: {external_dict}") # Debug log
            print(f"internal_dict: {internal_dict}") # Debug log
            print(f"combined: {combined}") # Debug log
            # Assertions based on the mocked walk_dir output
            expected_external = {
                'library/modelA': ['tag1', 'tag2'],
                'user/modelB': ['latest']
            }
            expected_internal = {
                'library/modelA': ['tag2'],
                'custom/modelC': ['v1']
            }
            expected_combined = [
                ['library/modelA', ['tag1', 'tag2'], ['tag2']],
                ['user/modelB', ['latest'], []],
                ['custom/modelC', [], ['v1']]
            ]
            # Sort lists within combined for consistent comparison
            for item in expected_combined:
                item[1].sort()
                item[2].sort()
            for item in combined:
                item[1].sort()
                item[2].sort()

            # Sort combined lists by model name for consistent comparison
            expected_combined.sort(key=lambda x: x[0])
            combined.sort(key=lambda x: x[0])

            self.assertEqual(external_dict, expected_external)
            self.assertEqual(internal_dict, expected_internal)
            self.assertEqual(combined, expected_combined)

    @patch('builtins.input', return_value='yes')
    def test_get_user_confirmation_yes(self, input):
        self.assertTrue(ollamautil_module.get_user_confirmation("Test prompt"))

    @patch('builtins.input', return_value='y')
    def test_get_user_confirmation_y(self, input):
        self.assertTrue(ollamautil_module.get_user_confirmation("Test prompt"))

    @patch('builtins.input', return_value='no')
    def test_get_user_confirmation_no(self, input):
        self.assertFalse(ollamautil_module.get_user_confirmation("Test prompt"))

    @patch('builtins.input', return_value='n')
    def test_get_user_confirmation_n(self, input):
        self.assertFalse(ollamautil_module.get_user_confirmation("Test prompt"))

    @patch('builtins.input', side_effect=['maybe', 'yes'])
    def test_get_user_confirmation_invalid_then_yes(self, input):
        self.assertTrue(ollamautil_module.get_user_confirmation("Test prompt"))

    def test_get_curnow_cache(self):
        # Example test case for get_curnow_cache
        pass

    def test_toggle_int_ext_cache(self):
        # Example test case for toggle_int_ext_cache
        pass

    def test_select_models(self):
        # Example test case for select_models
        pass

    def test_pull_models(self):
        # Example test case for pull_models
        pass

    def test_push_models(self):
        # Example test case for push_models
        pass

    def test_migrate_cache_user(self):
        # Example test case for migrate_cache_user
        pass

    def test_migrate_cache(self):
        # Example test case for migrate_cache
        pass

    def test_copy_blob_files(self):
        # Example test case for copy_blob_files
        pass

    def test_validate_blob_sha256(self):
        # Example test case for validate_blob_sha256
        pass

    def test_copy_metadata(self):
        # Example test case for copy_metadata
        pass

    def test_remove_from_cache(self):
        # Example test case for remove_from_cache
        pass

    def test_ftStr(self):
        # Example test case for ftStr
        pass


if __name__ == '__main__':
    unittest.main()
