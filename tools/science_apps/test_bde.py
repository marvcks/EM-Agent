"""BDE contract and chemistry tests; no model weights or Psi4 required."""
import json
import zipfile
import unittest
import tempfile
import os
from pathlib import Path
from tools.science_apps.service import JobRequest, prepare_input


class BDEContractTests(unittest.TestCase):
    def test_two_modes_and_name_input_have_their_own_contract(self):
        for method in ['ALFABET', 'Psi4']:
            request = JobRequest(app_id='bde', task='bde', smiles='CCO', method=method)
            name, content, args = prepare_input(request)
            self.assertEqual(name, 'request.json')
            self.assertEqual(json.loads(content)['method'], method)
            self.assertEqual(args, ['request.json'])
        request = JobRequest(app_id='bde', task='bde', compound_name='ethanol', input_kind='name')
        self.assertEqual(json.loads(prepare_input(request)[1])['compound_name'], 'ethanol')
        for change in [{'xyz': '3\nwater\nO 0 0 0\nH 0 0 1\nH 0 1 0'}, {'charge': 1},
                       {'task': 'energy'}, {'smiles': 'CCO.O'}, {'smiles': ''},
                       {'compound_name': 'ethanol'}, {'basis': 'STO-3G'}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                prepare_input(JobRequest(app_id='bde', task='bde', smiles='CCO').model_copy(update=change))


class BDEChemistryTests(unittest.TestCase):
    # @spec BDE-002 — Explicit-H radicals and unsupported bonds
    def test_explicit_hydrogens_radicals_and_unsupported_bonds(self):
        from tools.science_apps.bde_runner import parse_molecule, enumerate_bonds
        molecule = parse_molecule('CC=O')
        rows, fragments = enumerate_bonds(molecule)
        self.assertEqual(len(rows), molecule.GetNumBonds())
        self.assertEqual(sum(row['status'] == 'unsupported' for row in rows), 1)
        self.assertEqual(len(fragments), 5)
        for pair in fragments.values():
            self.assertEqual(sum(m.GetNumAtoms() for m in pair), molecule.GetNumAtoms())
            self.assertTrue(all(sum(a.GetNumRadicalElectrons() for a in m.GetAtoms()) == 1 for m in pair))
        ring_rows, _ = enumerate_bonds(parse_molecule('C1CC1'))
        self.assertEqual(sum(r['reason'] == 'ring_bond' for r in ring_rows), 3)
        for bad in ['[Na+].[Cl-]', '[CH3]', 'CCl', '[NH4+]', 'C' * 129]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_molecule(bad)

    def test_download_bundle_contains_generated_radical_coordinates_and_bond_graph(self):
        from tools.science_apps.bde_runner import parse_molecule, enumerate_bonds, export_generated_structures, write_outputs, archive_outputs
        molecule = parse_molecule('CC=O')
        rows, _ = enumerate_bonds(molecule)
        for row in rows:
            if row['status'] == 'pending':
                row.update(status='ok', bde_kcal_mol=100.0)
        result = {'bonds': rows, 'minimum_bond_index': 0}
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                export_generated_structures(molecule)
                write_outputs(molecule, result)
                Path('scratch').mkdir()
                Path('scratch/private-temporary-data').write_text('temporary')
                archive_outputs()
                with zipfile.ZipFile('results.zip') as archive:
                    names = archive.namelist()
                    self.assertIsNone(archive.testzip())
                    self.assertTrue(any(name.startswith('generated-fragments/') for name in names))
                    self.assertFalse(any(name.startswith('scratch/') for name in names))
                mapping = json.loads(Path('fragment-structures.json').read_text())['bond_to_xyz']
                self.assertEqual(len(mapping), 5)
                for names in mapping.values():
                    counts = [int((Path('generated-fragments') / name).read_text().splitlines()[0]) for name in names]
                    self.assertEqual(sum(counts), molecule.GetNumAtoms())
                self.assertTrue(Path('molecule.png').read_bytes().startswith(b'\x89PNG'))
                self.assertIn('multiple_bond', Path('bonds.csv').read_text())
            finally:
                os.chdir(previous)

    def test_result_rejects_missing_nan_and_wrong_minimum(self):
        from tools.science_apps.bde_runner import verified_bde
        result = {'verified': True, 'mode': 'ALFABET', 'unit': 'kcal/mol', 'canonical_smiles': 'C',
                  'bonds': [{'bond_index': 0, 'status': 'ok', 'bde_kcal_mol': 104.0}],
                  'minimum_bond_index': 0, 'minimum_bde_kcal_mol': 104.0}
        self.assertTrue(verified_bde(result))
        for changes in [{'bonds': []}, {'minimum_bde_kcal_mol': 0}, {'minimum_bond_index': 2},
                        {'mode': 'unknown'}, {'bonds': [{'bond_index': 0, 'status': 'ok', 'bde_kcal_mol': float('nan')}]}]:
            self.assertFalse(verified_bde({**result, **changes}))


if __name__ == '__main__':
    unittest.main()
