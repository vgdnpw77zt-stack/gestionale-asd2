"""A355 film studio: two-athlete auth, CSRF, media download and local audio safety."""
import importlib.util
import sqlite3
import tempfile
import unittest
import shutil
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
ALBUM=load('bootstrap/bodymind_a351_private_album.py','a355_test_album')
STUDIO=load('bootstrap/bodymind_a355_film_studio.py','a355_test_studio')
A='A355_TEST_FAMILY_ALPHA_9292828181'
B='A355_TEST_FAMILY_BRAVO_8181929393'

def picture():
    memory=BytesIO()
    Image.new('RGB',(220,320),(30,112,122)).save(memory,'PNG')
    return memory.getvalue()

class TwoFamilyFilmStudio(unittest.TestCase):
    def setUp(self):
        self.sandbox=tempfile.TemporaryDirectory(prefix='bm355_')
        self.base=Path(self.sandbox.name)
        self.admin=self.base/'admin_ro.sqlite'
        with sqlite3.connect(self.admin) as db:
            db.executescript("""CREATE TABLE tesserati
              (id INTEGER PRIMARY KEY,online_token TEXT UNIQUE NOT NULL);
              INSERT INTO tesserati VALUES(1,'A355_TEST_FAMILY_ALPHA_9292828181');
              INSERT INTO tesserati VALUES(2,'A355_TEST_FAMILY_BRAVO_8181929393');""")
        self.app=Flask('A355_TEST')
        self.app.secret_key='test-only-not-production'
        self.app.config['TESTING']=True
        self.mount=patch.object(ALBUM,'ROOT',self.base/'gallery')
        self.mount.start()
        def provider():
            return sqlite3.connect(self.admin.resolve().as_uri()+'?mode=ro',uri=True)
        ALBUM.install_family_gallery(self.app,provider)
        STUDIO.install_family_film_studio(self.app,provider,ALBUM)
        self.client=self.app.test_client()

    def tearDown(self):
        self.mount.stop()
        self.sandbox.cleanup()

    def path(self,token=A,ending=''):
        return '/app-tesserato/'+token+'/studio'+ending

    def upload(self,token=A):
        return self.client.post('/app-tesserato/'+token+'/album/upload',data={
           'csrf':ALBUM._csrf(self.app,token),'privacy':'yes',
           'photos':(BytesIO(picture()),'synthetic.png')
        },content_type='multipart/form-data')

    def photos(self):
        with sqlite3.connect(ALBUM.ROOT/'albums.sqlite3') as db:
            return [r[0] for r in db.execute('SELECT id FROM photos WHERE athlete_id=1 ORDER BY created_at,id')]

    def request_movie(self,token=A,**fields):
        default={'csrf':ALBUM._csrf(self.app,token),'style':'eden',
                 'music':'original','title':'Gaia','photos':self.photos()}
        default.update(fields)
        return self.client.post(self.path(token,'/render'),data=default,
                                content_type='multipart/form-data')

    def test_without_images_is_private_and_no_album_created(self):
        response=self.client.get(self.path())
        self.assertEqual(response.status_code,200)
        self.assertIn('no-store',response.headers['Cache-Control'])
        self.assertIn('Il mio film',response.get_data(as_text=True))
        self.assertEqual(self.client.get(self.path('WRONG_GUESS_THE_TOKEN_929292')).status_code,404)
        self.assertEqual(self.client.get(self.path(B,'/film')).status_code,404)
        self.assertFalse((ALBUM.ROOT/'albums.sqlite3').exists())

    def test_album_links_to_studio_and_anti_cross_tenant(self):
        self.assertEqual(self.upload().status_code,303)
        album=self.client.get('/app-tesserato/'+A+'/album').get_data(as_text=True)
        self.assertIn('/studio',album)
        studio=self.client.get(self.path()).get_data(as_text=True)
        self.assertIn(self.photos()[0],studio)
        self.assertNotIn(self.photos()[0],self.client.get(self.path(B)).get_data(as_text=True))
        self.assertEqual(self.request_movie(token=B).status_code,404)

    def test_rejects_forged_posts_rights_and_unapproved_music(self):
        self.assertEqual(self.upload().status_code,303)
        self.assertEqual(self.request_movie(csrf='forged').status_code,403)
        self.assertEqual(self.request_movie(title='<script>bad</script>').status_code,400)
        self.assertEqual(self.request_movie(style='unknown').status_code,400)
        self.assertEqual(self.request_movie(music='own').status_code,400)
        self.assertEqual(self.request_movie(music='own',rights='yes',audio=(BytesIO(b'bad'),'music.mp3')).status_code,415)
        self.assertEqual(self.request_movie(photos=['f'*30]).status_code,404)
        cross=self.client.post(self.path(B,'/delete'),
                               data={'csrf':ALBUM._csrf(self.app,A)})
        self.assertEqual(cross.status_code,403)

    def test_original_soundtrack_is_local_and_distinct(self):
        if not shutil.which('ffmpeg'):
            self.skipTest('No FFmpeg in this runner')
        with tempfile.TemporaryDirectory(prefix='bm355_music_') as directory:
            paths=[]
            for style in sorted(STUDIO.ALLOWED_STYLES):
                target=Path(directory)/(style+'.wav')
                STUDIO._original_music(target,3.1,style)
                self.assertGreater(target.stat().st_size,120000)
                paths.append(target.read_bytes()[44:5044])
            self.assertEqual(len(set(paths)),3)

    def test_video_generation_owner_download_and_erase(self):
        if not Path('/usr/bin/ffmpeg').is_file():
            self.skipTest('FFmpeg unavailable here')
        self.assertEqual(self.upload().status_code,303)
        result=self.request_movie()
        self.assertEqual(result.status_code,303,result.get_data(as_text=True)[:200])
        film=self.client.get(self.path(A,'/film'))
        self.assertEqual(film.status_code,200)
        self.assertEqual(film.mimetype,'video/mp4')
        self.assertGreater(len(film.data),8000)
        self.assertEqual(self.client.get(self.path(B,'/film')).status_code,404)
        download=self.client.get(self.path(A,'/download'))
        self.assertEqual(download.status_code,200)
        self.assertIn('attachment',download.headers['Content-Disposition'])
        self.assertIn('no-store',download.headers['Cache-Control'])
        removed=self.client.post(self.path(A,'/delete'),
            data={'csrf':ALBUM._csrf(self.app,A)})
        self.assertEqual(removed.status_code,303)
        self.assertEqual(self.client.get(self.path(A,'/film')).status_code,404)
        self.assertEqual(len(self.photos()),1)

if __name__=='__main__':
    unittest.main()
