"""Crystal-morphology contract tests; no model weights required."""
import json
import unittest

from tools.science_apps.service import JobRequest, prepare_input


class MorphologyContractTests(unittest.TestCase):
    # @spec CM-002 — Fixed five-parameter contract for single and batch input
    def test_single_and_batch_requests_have_their_own_contract(self):
        single = JobRequest(app_id='crystal-morphology', task='classification',
                            input_mode='single', additive_percent=1.0,
                            antisolvent_temp_c=10, stirring_rpm=300,
                            concentration_g_ml=0.06, solvent_ratio=0.125)
        name, content, args = prepare_input(single)
        self.assertEqual((name, args), ('request.json', ['request.json']))
        # An empty method resolves to the catalog default, auto model selection.
        self.assertEqual(json.loads(content)['method'], 'auto')
        batch = JobRequest(app_id='crystal-morphology', task='classification',
                           input_mode='batch', method='CatBoost',
                           table_csv='添加剂百分比,反溶剂温度(°C),搅拌速率(rpm),浓度(g/ml),溶剂/反溶剂比值\n1,10,300,0.06,0.125\n')
        self.assertEqual(prepare_input(batch)[0], 'request.json')
        for changes in [{'xyz': '3\nwater\nO 0 0 0\nH 0 0 1\nH 0 1 0'},
                        {'smiles': 'CCO'}, {'charge': 1}, {'multiplicity': 2},
                        {'task': 'energy'}, {'method': 'arbitrary'},
                        {'input_mode': 'single', 'additive_percent': None},
                        {'input_mode': 'single', 'antisolvent_temp_c': 200.0},
                        {'input_mode': 'batch', 'table_csv': ''},
                        {'input_mode': 'batch', 'additive_percent': 1.0},
                        {'basis': 'STO-3G'}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                prepare_input(single.model_copy(update=changes) if 'input_mode' not in changes
                              else JobRequest(**{**single.model_dump(), **changes}))

    def test_rows_are_parsed_strictly_with_bounds_and_limits(self):
        from tools.science_apps.morphology_runner import MAX_BATCH_ROWS, parse_batch_rows
        header = '添加剂百分比,反溶剂温度(°C),搅拌速率(rpm),浓度(g/ml),溶剂/反溶剂比值'
        rows = parse_batch_rows(header + '\n1,10,300,0.06,0.125\n5,5,300,0.06,0.167\n')
        self.assertEqual(rows, [[1.0, 10.0, 300.0, 0.06, 0.125], [5.0, 5.0, 300.0, 0.06, 0.167]])
        with self.assertRaises(ValueError):
            parse_batch_rows(header + ',真实形貌\n1,10,300,0.06,0.125,球\n')
        too_many = header + '\n' + '\n'.join('1,10,300,0.06,0.125' for _ in range(MAX_BATCH_ROWS + 1))
        for bad in ['', header, header + '\n1,10,300,0.06', header + '\n1,10,300,0.06,0.125,9',
                    header + '\n1,10,300,nan,0.125', header + '\n1,10,300,inf,0.125',
                    header + '\n1,10,300,0.06,9', header + '\nnan,10,300,0.06,0.125',
                    '添加剂百分比,搅拌速率(rpm)\n1,300', too_many]:
            with self.subTest(bad=bad[:40]), self.assertRaises(ValueError):
                parse_batch_rows(bad)

    def test_result_verification_rejects_incomplete_or_mismatched_rows(self):
        from tools.science_apps.morphology_runner import verified_morphology
        request = JobRequest(app_id='crystal-morphology', task='classification',
                             input_mode='single', additive_percent=1.0,
                             antisolvent_temp_c=10, stirring_rpm=300,
                             concentration_g_ml=0.06, solvent_ratio=0.125)
        features = {'添加剂百分比': 1.0, '反溶剂温度(°C)': 10.0, '搅拌速率(rpm)': 300.0,
                    '浓度(g/ml)': 0.06, '溶剂/反溶剂比值': 0.125}
        row = {'index': 1, 'features': features, 'predicted_label': '球',
               'probabilities': {'其他': 0.2, '球': 0.7, '针': 0.1}, 'in_training_range': True}
        result = {'verified': True, 'app_id': 'crystal-morphology', 'model_id': 'CatBoost',
                  'class_order': ['其他', '球', '针'], 'prediction_count': 1,
                  'class_counts': {'其他': 0, '球': 1, '针': 0}, 'rows': [row]}
        self.assertTrue(verified_morphology(result, request))
        for changes in [{'verified': False}, {'model_id': 'unknown'}, {'class_counts': {'其他': 1, '球': 0, '针': 0}},
                        {'prediction_count': 2}, {'rows': []},
                        {'rows': [{**row, 'probabilities': {'其他': 0.2, '球': 0.7, '针': 0.2}}]},
                        {'rows': [{**row, 'predicted_label': '立方'}]},
                        {'rows': [{**row, 'in_training_range': 'yes'}]}]:
            self.assertFalse(verified_morphology({**result, **changes}, request))


if __name__ == '__main__':
    unittest.main()
