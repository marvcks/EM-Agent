"""Scientific queue contract; numerical FEM tests live with the standalone solver."""
import unittest
from types import SimpleNamespace

from tools.science_apps.cnt2d_runner import validate_cnt2d, verified_cnt2d


def request(**values):
    return SimpleNamespace(app_id='cnt2d', task='conduction', method='FEM-P2', basis='',
                           xyz='', smiles='', document_name='', table_csv='', charge=0,
                           multiplicity=1, cnt_parameters=values.get('parameters'),
                           cnt_corners=values.get('corners', ''), cnt_seed=20260901)


class CNT2DTests(unittest.TestCase):
    # @spec CNT2D-005 — Bounded non-molecular input, never user scripts or XYZ.
    def test_parameters_and_mesh_budgets(self):
        p = validate_cnt2d(request())
        self.assertEqual(p['filler_area_fraction_target'], 0.01)
        self.assertEqual(p['cnt_k'], 400)
        for changes in [{'cnt_k': float('nan')}, {'surface_width': 0.5},
                        {'bulk_size': 0.001}, {'interface_layers': 100},
                        {'filler_area_fraction_target': 0.8}, {'output_folder': '/tmp'},
                        {'box_size': True}, {'cnt_length': 0.001}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_cnt2d(request(parameters=changes))
        r = request()
        r.xyz = 'not a molecular input'
        with self.assertRaises(ValueError):
            validate_cnt2d(r)

    def test_corner_import_is_bounded_and_requires_rectangular_rows(self):
        header = 'CNT_ID\tx1\ty1\tx2\ty2\tx3\ty3\tx4\ty4\n'
        row = '1\t1\t1\t11\t1\t11\t2\t1\t2\n'
        validate_cnt2d(request(corners=header + row))
        for text in [row, header + row * 65, header + row.replace('11\t2', '12\t2'),
                     header + row.replace('11', 'nan')]:
            with self.subTest(text=text[:60]), self.assertRaises(ValueError):
                validate_cnt2d(request(corners=text))

    # @spec CNT2D-006 — A successful process cannot publish mismatched/unverified metrics.
    def test_result_requires_physics_checks_and_matching_parameters(self):
        r = request()
        result = {'verified': True, 'app_id': 'cnt2d', 'unit': 'W/(m K)',
                  'parameters': validate_cnt2d(r), 'seed': r.cnt_seed,
                  'metrics': {'Keff_X': .15, 'CNT_Number': 10, 'Triangles': 1000,
                              'Energy_Balance_Error': 1e-9, 'Free_Residual_Relative': 1e-10,
                              'Heatflow_Left': -3., 'Heatflow_Right': 3.,
                              'Matrix_Area_Fraction_Mesh': .99, 'Core_Area_Fraction_Mesh': .00784,
                              'Interface_Area_Fraction_Mesh': .00216}}
        self.assertTrue(verified_cnt2d(result, r))
        for patch in [{'verified': False}, {'unit': 'eV'}, {'parameters': {}},
                      {'metrics': {**result['metrics'], 'Keff_X': float('nan')}},
                      {'metrics': {**result['metrics'], 'CNT_Number': 500}}]:
            self.assertFalse(verified_cnt2d({**result, **patch}, r))
