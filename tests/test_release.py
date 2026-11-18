import importlib.util, io, json, sys, tarfile, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('release',ROOT/'tools/release.py');release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)

class Release(unittest.TestCase):
    def test_archive_is_deterministic_and_excludes_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            a=Path(temp)/'a.tar.gz';b=Path(temp)/'b.tar.gz'
            release.build(a);release.build(b);self.assertEqual(a.read_bytes(),b.read_bytes())
            with tarfile.open(a) as tar:
                names=[p.name.split('/',1)[1] for p in tar.getmembers()]
                self.assertIn('MANIFEST.sha256',names);self.assertIn('examples/observable-echo/LICENSE',names)
                for name in names:
                    self.assertNotIn(name.split('/')[0],{'local','dist','secrets','state','runs','diagnostics'})
                    self.assertFalse(name.endswith(('.pyc','.pdb','.sys','.exe','.iso','.qcow2','.zip')))
    def test_publication_tree_rejects_secret_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'docs').mkdir();(root/'docs'/'private.pem').write_text('not allowed')
            with self.assertRaisesRegex(ValueError,'Unexpected publication'):release.files(root)
    def test_publication_tree_rejects_key_in_text(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'docs').mkdir()
            key='-----BEGIN '+'OPENSSH PRIVATE KEY-----'
            (root/'docs'/'notes.md').write_text(key)
            with self.assertRaisesRegex(ValueError,'Private key'):release.files(root)
    def test_publication_tree_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'docs').mkdir();(root/'docs'/'notes.md').symlink_to('/etc/passwd')
            with self.assertRaisesRegex(ValueError,'symlink'):release.files(root)

if __name__=='__main__':unittest.main()
