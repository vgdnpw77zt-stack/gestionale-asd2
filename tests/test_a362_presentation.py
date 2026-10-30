import ast,collections,hashlib,importlib.util,re,unittest
from pathlib import Path
p=Path('bootstrap/family_a362_runtime.py')
spec=importlib.util.spec_from_file_location('scene',p);scene=importlib.util.module_from_spec(spec);spec.loader.exec_module(scene)
class Presentation(unittest.TestCase):
 def setUp(self):
  self.old=Path('/tmp/bm-template.html').read_text();self.new=scene.compose(self.old)
 def test_business_template_and_actions_preserved(self):
  strip=lambda s:re.sub(r'<script\b.*?</script>','',s,flags=re.S)
  old,new=strip(self.old),strip(self.new)
  for pattern in (r'\{[{%].*?[}%]\}',r'(?:href|action)="([^"]+)"'):
   self.assertFalse(collections.Counter(re.findall(pattern,old,re.S))-collections.Counter(re.findall(pattern,new,re.S)))
 def test_known_source_and_isolation(self):
  self.assertEqual(self.new.count('<style'),1)
  self.assertNotIn('BODYMIND A359',self.new)
  self.assertNotIn('bodymind-a349-native-ratio',self.new)
  dirty=self.new.replace('</body>','<style id="a239">body{background:purple!important}</style><script id="bodymind-a361-probe" src="/_bodymind_a361_probe.js"></script><link rel="stylesheet" href="/_bodymind_family_a360.css"></body>')
  cleaned=scene.clean_response_markup(dirty)
  self.assertNotIn('a239',cleaned);self.assertNotIn('_bodymind_a361_probe',cleaned);self.assertNotIn('_bodymind_family_a360.css',cleaned)
  self.assertIn('bm362-controls',cleaned);self.assertIn('csrf',cleaned)
  self.assertEqual(scene.clean_response_markup('<html><style>admin</style></html>'),'<html><style>admin</style></html>')
 def test_unknown_source_rejected(self):
  with self.assertRaises(RuntimeError):scene.compose(self.old+' ')
if __name__=='__main__':unittest.main()
