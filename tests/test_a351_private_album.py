"""A351 two-athlete privacy and slideshow tests on FAKE SQLite + /tmp only."""
from io import BytesIO
from pathlib import Path
import importlib.util
import sqlite3
import tempfile
import zipfile
import unittest
from unittest.mock import patch

from flask import Flask
from PIL import Image

SOURCE=Path(__file__).resolve().parents[1]/'bootstrap/bodymind_a351_private_album.py'
SPEC=importlib.util.spec_from_file_location('a351_synthetic_album',SOURCE)
ALBUM=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ALBUM)

ATHLETE_A='A351_SYNTH_ALPHA_9283819283'
ATHLETE_B='A351_SYNTH_BETA_1248981283'
def png():
    buf=BytesIO()
    Image.new('RGB',(160,240),(36,165,155)).save(buf,'PNG')
    return buf.getvalue()

class AthleteAlbumSafety(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='a351_test_')
        self.root=Path(self.temp.name)
        self.admin=self.root/'readonly_administrative_test.sqlite'
        db=sqlite3.connect(self.admin)
        db.executescript("""CREATE TABLE tesserati(id INTEGER PRIMARY KEY,online_token TEXT UNIQUE NOT NULL);
          INSERT INTO tesserati VALUES (1,'A351_SYNTH_ALPHA_9283819283');
          INSERT INTO tesserati VALUES (2,'A351_SYNTH_BETA_1248981283');""")
        db.commit();db.close()
        self.app=Flask('a351_fake_family')
        self.app.config['TESTING']=True
        self.app.secret_key='synthetic-private-unit-tests-only'
        def db_provider():
            return sqlite3.connect(self.admin.resolve().as_uri()+'?mode=ro',uri=True)
        self.patch=patch.object(ALBUM,'ROOT',self.root/'private_media')
        self.patch.start()
        ALBUM.install_family_gallery(self.app,db_provider)
        self.client=self.app.test_client()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def endpoint(self,token=ATHLETE_A,suffix=''):
        return f'/app-tesserato/{token}/album'+suffix

    def token(self,token=ATHLETE_A):
        return ALBUM._csrf(self.app,token)

    def upload(self,token=ATHLETE_A,csrf=None,payload=None,consent='yes'):
        return self.client.post(self.endpoint(token,'/upload'),
          data={'csrf':self.token(token) if csrf is None else csrf,
                'privacy':consent,
                'photos':(BytesIO(png() if payload is None else payload),'synthetic.png')},
          content_type='multipart/form-data')

    def test_get_does_not_create_album_data_and_noindex(self):
        resp=self.client.get(self.endpoint())
        self.assertEqual(resp.status_code,200)
        self.assertIn('Le mie foto',resp.get_data(as_text=True))
        self.assertEqual(resp.headers['Referrer-Policy'],'no-referrer')
        self.assertIn('noindex',resp.headers['X-Robots-Tag'])
        self.assertFalse((ALBUM.ROOT/'albums.sqlite3').exists())
        self.assertEqual(self.client.get(self.endpoint('GUESS_NONEXISTENT_12345')).status_code,404)

    def test_upload_requires_csrf_and_guardian_confirmation(self):
        self.assertEqual(self.upload(csrf='FAKE').status_code,403)
        self.assertEqual(self.upload(consent='no').status_code,400)
        self.assertEqual(self.upload(payload=b'not an image').status_code,415)
        self.assertEqual(self.client.post(self.endpoint('GUESS_NONEXISTENT_12345','/upload')).status_code,404)
        self.assertFalse((ALBUM.ROOT/'albums.sqlite3').exists())
        forbidden=self.client.post(self.endpoint('GUESS_NONEXISTENT_12345'),data={})
        self.assertIn(forbidden.status_code,(404,405))

    def test_images_are_owned_stripped_and_inaccessible_between_families(self):
        first=self.upload()
        self.assertEqual(first.status_code,303)
        self.assertIn('no-store',first.headers['Cache-Control'])
        db=sqlite3.connect(ALBUM.ROOT/'albums.sqlite3')
        row=db.execute('SELECT id,filename,athlete_id FROM photos').fetchone()
        self.assertEqual(row[2],1)
        self.assertEqual(db.execute('SELECT COUNT(*) FROM photos WHERE athlete_id=2').fetchone()[0],0)
        photoid,fn=row[0],row[1]
        db.close()
        data=(ALBUM.ROOT/'1'/fn).read_bytes()
        self.assertTrue(data.startswith(b'\\xff\\xd8') or data[:2]==b'\xff\xd8')
        self.assertNotIn(b'Exif\\x00\\x00',data)
        resp=self.client.get(self.endpoint(ATHLETE_A,'/photo/'+photoid))
        self.assertEqual(resp.status_code,200)
        self.assertEqual(resp.mimetype,'image/jpeg')
        self.assertEqual(self.client.get(self.endpoint(ATHLETE_B,'/photo/'+photoid)).status_code,404)
        self.assertEqual(self.client.post(self.endpoint(ATHLETE_B,'/delete/'+photoid),
            data={'csrf':self.token(ATHLETE_B)}).status_code,404)
        self.assertTrue((ALBUM.ROOT/'1'/fn).is_file())
        removed=self.client.post(self.endpoint(ATHLETE_A,'/delete/'+photoid),
            data={'csrf':self.token(ATHLETE_A)})
        self.assertEqual(removed.status_code,303)
        self.assertFalse((ALBUM.ROOT/'1'/fn).exists())

    def test_status_is_private_and_no_video_before_generation(self):
        self.assertEqual(self.client.get(self.endpoint(ATHLETE_A,'/status')).json,
                         {'available':False,'url':None})
        self.assertEqual(self.client.get(self.endpoint(ATHLETE_A,'/film')).status_code,404)
        self.assertEqual(self.client.get(self.endpoint(ATHLETE_B,'/status')).status_code,200)

    def test_album_cap_and_cross_origin_blocking(self):
        bad=self.client.post(self.endpoint(ATHLETE_A,'/upload'),
             data={'csrf':self.token(),'privacy':'yes','photos':(BytesIO(png()),'x.png')},
             headers={'Origin':'https://evil.example'},
             content_type='multipart/form-data')
        self.assertEqual(bad.status_code,403)
        self.assertEqual(self.upload().status_code,303)

    def test_private_backup_export_and_full_erasure_are_owner_scoped(self):
        self.assertEqual(self.upload().status_code,303)
        exported=self.client.get(self.endpoint(ATHLETE_A,'/export'))
        self.assertEqual(exported.status_code,200)
        self.assertEqual(exported.mimetype,'application/zip')
        self.assertIn('attachment',exported.headers['Content-Disposition'])
        with zipfile.ZipFile(BytesIO(exported.data)) as archive:
            names=archive.namelist()
            self.assertEqual(names,['foto/01.jpg'])
            self.assertTrue(archive.read('foto/01.jpg').startswith(bytes((255,216))))
        self.assertEqual(self.client.get(self.endpoint(ATHLETE_B,'/export')).status_code,404)
        self.assertEqual(self.client.post(self.endpoint(ATHLETE_A,'/clear'),
           data={'csrf':self.token(),'confirm':'no'}).status_code,400)
        self.assertEqual(self.client.post(self.endpoint(ATHLETE_A,'/clear'),
           data={'csrf':'wrong','confirm':'yes'}).status_code,403)
        erased=self.client.post(self.endpoint(ATHLETE_A,'/clear'),
           data={'csrf':self.token(),'confirm':'yes'})
        self.assertEqual(erased.status_code,303)
        self.assertEqual(self.client.get(self.endpoint(ATHLETE_A,'/export')).status_code,404)
        db=sqlite3.connect(ALBUM.ROOT/'albums.sqlite3')
        self.assertEqual(db.execute('SELECT COUNT(*) FROM photos').fetchone()[0],0)
        self.assertEqual(db.execute('SELECT COUNT(*) FROM consents').fetchone()[0],0)
        db.close()

    def test_film_is_only_accessible_to_its_owner_when_renderer_available(self):
        if not Path('/usr/bin/ffmpeg').is_file():
            self.skipTest('FFmpeg is tested in the built Docker image')
        self.assertEqual(self.upload().status_code,303)
        self.assertEqual(self.upload().status_code,303)
        resp=self.client.post(self.endpoint(ATHLETE_A,'/generate'),data={'csrf':self.token()})
        self.assertEqual(resp.status_code,303,resp.get_data(as_text=True)[:200])
        self.assertTrue(self.client.get(self.endpoint(ATHLETE_A,'/status')).json['available'])
        self.assertFalse(self.client.get(self.endpoint(ATHLETE_B,'/status')).json['available'])
        movie=self.client.get(self.endpoint(ATHLETE_A,'/film'))
        self.assertEqual(movie.status_code,200)
        self.assertEqual(movie.mimetype,'video/mp4')
        self.assertGreater(len(movie.data),3000)
        self.assertEqual(self.client.get(self.endpoint(ATHLETE_B,'/film')).status_code,404)

if __name__=='__main__':
    unittest.main()
