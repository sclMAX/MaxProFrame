import os, tempfile, unittest
from unittest.mock import patch
import FreeCAD as App
import test_t2_independent as independent
from test_t2_independent import rect, snap, cap, print

class CleanupOwnership(unittest.TestCase):
    setUp = independent.Independent.setUp
    tearDown = independent.Independent.tearDown
    def test_native_failure_cleanup_owns_only_its_file_fcbak(self):
        s,w,h=rect(self.d); b=snap(s); root=tempfile.mkdtemp(); newdoc=App.newDocument; sent=[]
        class FailureDoc:
            def __init__(self,d): self.d=d
            def __getattr__(self,n): return getattr(self.d,n)
            def saveAs(self,p):
                sections_dir=os.path.join(root,'sections')
                stem=os.path.splitext(os.path.basename(p))[0]
                unrelated=os.path.join(sections_dir,stem+'_unrelated.FCBak')
                open(unrelated,'wb').write(b'KEEP')
                sent.append(unrelated)
                open(p,'wb').write(b'partial')
                raise OSError('injected native disk write failure')
        def new(*args,**kw):
            d=newdoc(*args,**kw)
            return FailureDoc(d) if args and args[0]=='SectionAsset' else d
        with patch.object(cap.App,'newDocument',new):
            with self.assertRaisesRegex(OSError,'injected native disk write failure'): cap.save_section_asset(root,s)
        self.addCleanup(self.assertEqual,b,snap(s))
        print('FAILURE_CLEANUP_FCBAK',os.listdir(os.path.join(root,'sections')), 'sentinel_exists',os.path.exists(sent[0]),flush=True)
        self.assertTrue(os.path.isfile(sent[0]),'unrelated prefix-sharing fcbak file deleted')
        self.assertEqual(open(sent[0],'rb').read(),b'KEEP')
