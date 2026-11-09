"""A370 regression tests use temporary synthetic files only."""
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest

flask=types.ModuleType('flask')
flask.abort=lambda code:None
flask.make_response=lambda *args:None
flask.request=None
sys.modules.setdefault('flask',flask)

target=Path(__file__).parents[1]/'bootstrap'/'a370_asd_folder_browser.py'
spec=importlib.util.spec_from_file_location('a370',target)
a=importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)/'documenti_asd'
        self.root.mkdir()
        (self.root/'VERBALI').mkdir()
        (self.root/'DOCUMENTI_ASD').mkdir()
        (self.root/'Statuto_e_atti').mkdir()
        (self.root/'DOCUMENTI_ASD'/'VERBALE_DI_ASSEMBLEA_COMPRESSO.pdf').write_bytes(b'%PDF-1.4 original')
        (self.root/'Statuto_e_atti'/'accordo prova.docx').write_bytes(b'word original')
        self.baseline=self.fingerprint()
    def tearDown(self):self.temp.cleanup()
    def fingerprint(self):
        result={}
        for p in self.root.rglob('*'):
            if p.is_file():result[str(p.relative_to(self.root))]=hashlib.sha256(p.read_bytes()).hexdigest()
        return result

    def test_all_original_folders_visible(self):
        _,folders,files=a.list_folder(self.root)
        self.assertEqual({f['name'] for f in folders},{'VERBALI','DOCUMENTI_ASD','Statuto_e_atti'})
        self.assertEqual(len(files),0)
    def test_empty_folder_is_not_hidden(self):
        _,folders,files=a.list_folder(self.root,'VERBALI')
        self.assertEqual((folders,files),([],[]))
        self.assertIn('Nessun file',a.render_archive(self.root,'VERBALI'))
    def test_verbale_listed_by_exact_filename(self):
        _,folders,files=a.list_folder(self.root,'DOCUMENTI_ASD')
        self.assertEqual(files[0]['name'],'VERBALE_DI_ASSEMBLEA_COMPRESSO.pdf')
    def test_download_link_uses_existing_route(self):
        s=a.render_archive(self.root,'DOCUMENTI_ASD')
        self.assertIn('/documenti/asd/download/DOCUMENTI_ASD/VERBALE_DI_ASSEMBLEA_COMPRESSO.pdf',s)
        self.assertIn('/documenti/asd/preview/DOCUMENTI_ASD/VERBALE_DI_ASSEMBLEA_COMPRESSO.pdf',s)
    def test_nested_and_encoded_filenames(self):
        s=a.render_archive(self.root,'Statuto_e_atti')
        self.assertIn('accordo%20prova.docx',s)
    def test_parent_traversal_rejected(self):
        for x in ['..','../','../private','VERBALI/../../secrets','/tmp','VERBALI\\..','VERBALI//x','.hidden','VERBALI/.hidden']:
            with self.subTest(x=x),self.assertRaises(ValueError):a.safe_folder(self.root,x)
    def test_unknown_folder_error(self):
        with self.assertRaises(FileNotFoundError):a.safe_folder(self.root,'non-existing')
    def test_filesystem_unchanged_after_all_reads(self):
        for p in ['', 'VERBALI','DOCUMENTI_ASD','Statuto_e_atti']:
            a.render_archive(self.root,p)
        self.assertEqual(self.baseline,self.fingerprint())
    def test_folders_and_files_named_safely(self):
        (self.root/'Statuto_e_atti'/'<x>.pdf').write_text('mock')
        s=a.render_archive(self.root,'Statuto_e_atti')
        self.assertNotIn('<x>.pdf',s)
        self.assertIn('&lt;x&gt;.pdf',s)
    def test_symlink_outside_archive_is_not_listed(self):
        other=Path(self.temp.name)/'outside'
        other.mkdir()
        (other/'private.pdf').write_text('private mock')
        (self.root/'external').symlink_to(other,target_is_directory=True)
        folders,files=a.list_folder(self.root)[1:]
        self.assertNotIn('external',{x['name'] for x in folders})
        with self.assertRaises(ValueError):a.safe_folder(self.root,'external')
    def test_no_delete_mutations_exposed(self):
        html=a.render_archive(self.root)
        self.assertNotIn('<form method="POST"',html)
        self.assertNotIn('Elimina</button>',html)

if __name__=='__main__':unittest.main()
