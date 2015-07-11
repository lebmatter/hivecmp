"""Utilities for comparing files and directories.

Classes:
    hivecmp

Functions:
    cmp(f1, f2, shallow=1) -> int
    cmpfiles(a, b, common) -> ([], [], [])

"""

import os
import stat
from itertools import ifilter, ifilterfalse, imap, izip
import ConfigParser
import shutil

__all__ = ["cmp","hivecmp","cmpfiles"]

_cache = {}
BUFSIZE=8*1024

def cmp(f1, f2, shallow=1):
    """Compare two files.

    Arguments:

    f1 -- First file name

    f2 -- Second file name

    shallow -- Just check stat signature (do not read the files).
               defaults to 1.

    Return value:

    True if the files are the same, False otherwise.

    This function uses a cache for past comparisons and the results,
    with a cache invalidation mechanism relying on stale signatures.

    """

    s1 = _sig(os.stat(f1))
    s2 = _sig(os.stat(f2))
    if s1[0] != stat.S_IFREG or s2[0] != stat.S_IFREG:
        return False
    if shallow and s1 == s2:
        return True
    if s1[1] != s2[1]:
        return False

    result = _cache.get((f1, f2))
    if result and (s1, s2) == result[:2]:
        return result[2]
    outcome = _do_cmp(f1, f2)
    _cache[f1, f2] = s1, s2, outcome
    return outcome

def _sig(st):
    return (stat.S_IFMT(st.st_mode),
            st.st_size,
            st.st_mtime)

def _do_cmp(f1, f2):
    bufsize = BUFSIZE
    fp1 = open(f1, 'rb')
    fp2 = open(f2, 'rb')
    while True:
        b1 = fp1.read(bufsize)
        b2 = fp2.read(bufsize)
        if b1 != b2:
            return False
        if not b1:
            return True

# Directory comparison class.
#
class hivecmp:
    """A class that manages the comparison of 2 directories.

    hivecmp(a,b,ignore=None,hide=None)
      A and B are directories.
      IGNORE is a list of names to ignore,
        defaults to ['RCS', 'CVS', 'tags'].
      HIDE is a list of names to hide,
        defaults to [os.curdir, os.pardir].

    High level usage:
      x = hivecmp(dir1, dir2)
      x.report() -> prints a report on the differences between dir1 and dir2
       or
      x.report_partial_closure() -> prints report on differences between dir1
            and dir2, and reports on common immediate subdirectories.
      x.report_full_closure() -> like report_partial_closure,
            but fully recursive.

    Attributes:
     left_list, right_list: The files in dir1 and dir2,
        filtered by hide and ignore.
     common: a list of names in both dir1 and dir2.
     left_only, right_only: names only in dir1, dir2.
     common_dirs: subdirectories in both dir1 and dir2.
     common_files: files in both dir1 and dir2.
     common_funny: names in both dir1 and dir2 where the type differs between
        dir1 and dir2, or the name is not stat-able.
     same_files: list of identical files.
     diff_files: list of filenames which differ.
     funny_files: list of files which could not be compared.
     subdirs: a dictionary of hivecmp objects, keyed by names in common_dirs.
     """

    def __init__(self, a, b, ignore=None, hide=None): # Initialize
        self.left = a
        self.right = b
        if hide is None:
            self.hide = [os.curdir, os.pardir] # Names never to be shown
        else:
            self.hide = hide
        if ignore is None:
            self.ignore = ['RCS', 'CVS', 'tags'] # Names ignored in comparison
        else:
            self.ignore = ignore

    def phase0(self): # Compare everything except common subdirectories
        self.left_list = _filter(os.listdir(self.left),
                                 self.hide+self.ignore)
        self.right_list = _filter(os.listdir(self.right),
                                  self.hide+self.ignore)
        self.left_list.sort()
        self.right_list.sort()

    def phase1(self): # Compute common names
        a = dict(izip(imap(os.path.normcase, self.left_list), self.left_list))
        b = dict(izip(imap(os.path.normcase, self.right_list), self.right_list))
        self.common = map(a.__getitem__, ifilter(b.__contains__, a))
        self.left_only = map(a.__getitem__, ifilterfalse(b.__contains__, a))
        self.right_only = map(b.__getitem__, ifilterfalse(a.__contains__, b))

    def phase2(self): # Distinguish files, directories, funnies
        self.common_dirs = []
        self.common_files = []
        self.common_funny = []

        for x in self.common:
            a_path = os.path.join(self.left, x)
            b_path = os.path.join(self.right, x)

            ok = 1
            try:
                a_stat = os.stat(a_path)
            except os.error, why:
                # print 'Can\'t stat', a_path, ':', why[1]
                ok = 0
            try:
                b_stat = os.stat(b_path)
            except os.error, why:
                # print 'Can\'t stat', b_path, ':', why[1]
                ok = 0

            if ok:
                a_type = stat.S_IFMT(a_stat.st_mode)
                b_type = stat.S_IFMT(b_stat.st_mode)
                if a_type != b_type:
                    self.common_funny.append(x)
                elif stat.S_ISDIR(a_type):
                    self.common_dirs.append(x)
                elif stat.S_ISREG(a_type):
                    self.common_files.append(x)
                else:
                    self.common_funny.append(x)
            else:
                self.common_funny.append(x)

    def phase3(self): # Find out differences between common files
        xx = cmpfiles(self.left, self.right, self.common_files)
        self.same_files, self.diff_files, self.funny_files = xx

    def phase4(self): # Find out differences between common subdirectories
        # A new hivecmp object is created for each common subdirectory,
        # these are stored in a dictionary indexed by filename.
        # The hide and ignore properties are inherited from the parent
        self.subdirs = {}
        for x in self.common_dirs:
            a_x = os.path.join(self.left, x)
            b_x = os.path.join(self.right, x)
            self.subdirs[x]  = hivecmp(a_x, b_x, self.ignore, self.hide)

    def phase4_closure(self): # Recursively call phase4() on subdirectories
        self.phase4()
        for sd in self.subdirs.itervalues():
            sd.phase4_closure()

    def report(self): # Print a report on the differences between a and b
        # Output format is purposely lousy
        print 'diff', self.left, self.right
        if self.left_only:
            self.left_only.sort()
            print 'Only in', self.left, ':', self.left_only
        if self.right_only:
            self.right_only.sort()
            print 'Only in', self.right, ':', self.right_only
        if self.same_files:
            self.same_files.sort()
            print 'Identical files :', self.same_files
        if self.diff_files:
            self.diff_files.sort()
            print 'Differing files :', self.diff_files
        if self.funny_files:
            self.funny_files.sort()
            print 'Trouble with common files :', self.funny_files
        if self.common_dirs:
            self.common_dirs.sort()
            print 'Common subdirectories :', self.common_dirs
        if self.common_funny:
            self.common_funny.sort()
            print 'Common funny cases :', self.common_funny

    def report_partial_closure(self): # Print reports on self and on subdirs
        self.report()
        for sd in self.subdirs.itervalues():
            print
            sd.report()

    def report_full_closure(self): # Report on self and subdirs recursively
        self.report()
        for sd in self.subdirs.itervalues():
            print
            sd.report_full_closure()

    ######################################
    ### Custom functions below
    ### report_patch, report_full_closure_patch, dump_hive_diff
    ### A hivepatch.ini will be created. Example below 
    ######################################
    # [Only]
    # hive2 = ['f3']
    # hive1/f1 = ['file2.txt']
    # hive2/f2 = ['d1', 'file5.py']

    # [Root]
    # old = hive1
    # new = hive2
    ######################################

    def report_patch(self):
        path_file_name = "hivepatch.ini"
        Config = ConfigParser.ConfigParser()
        
        if os.path.isfile(path_file_name):
            Config.read(path_file_name)

        #[Root] section to show names of old and new folders
        if not Config.has_section("Root"):
            Config.add_section("Root")
            Config.set('Root','old',self.left)
            Config.set('Root','new',self.right)

        #[Only] section shows inserted/deleted files
        if self.left_only:
            self.left_only.sort()
            print 'Only in', self.left, ':', self.left_only
            if not Config.has_section("Only"):
                Config.add_section("Only")
            Config.set('Only',self.left,self.left_only)
        if self.right_only:
            self.right_only.sort()
            print 'Only in', self.right, ':', self.right_only
            if not Config.has_section("Only"):
                Config.add_section("Only")
            Config.set('Only',self.right,self.right_only)

        patch_file = open(path_file_name,'w')
        Config.write(patch_file)
        patch_file.close()


    def report_full_closure_patch(self): # Report on self and subdirs recursively
        print self
        self.report_patch()
        for sd in self.subdirs.itervalues():
            print sd
            sd.report_full_closure_patch()


    def dump_hive_diff(self): # Report on self and subdirs recursively
        path_file_name = "hivepatch.ini"

        if os.path.isfile(path_file_name):
            Config = ConfigParser.ConfigParser()
            Config.read(path_file_name)
            diff_dir = Config.get('Root','new')+'-'+Config.get('Root','old')
            if os.path.exists(diff_dir):
                shutil.rmtree(diff_dir)
            os.mkdir(diff_dir)

        else:
            print "Hivepatch file doesn't exist!\
            Please run report_full_closure_patch to make one."
            return


    methodmap = dict(subdirs=phase4,
                     same_files=phase3, diff_files=phase3, funny_files=phase3,
                     common_dirs = phase2, common_files=phase2, common_funny=phase2,
                     common=phase1, left_only=phase1, right_only=phase1,
                     left_list=phase0, right_list=phase0)

    def __getattr__(self, attr):
        if attr not in self.methodmap:
            raise AttributeError, attr
        self.methodmap[attr](self)
        return getattr(self, attr)

def cmpfiles(a, b, common, shallow=1):
    """Compare common files in two directories.

    a, b -- directory names
    common -- list of file names found in both directories
    shallow -- if true, do comparison based solely on stat() information

    Returns a tuple of three lists:
      files that compare equal
      files that are different
      filenames that aren't regular files.

    """
    res = ([], [], [])
    for x in common:
        ax = os.path.join(a, x)
        bx = os.path.join(b, x)
        res[_cmp(ax, bx, shallow)].append(x)
    return res


# Compare two files.
# Return:
#       0 for equal
#       1 for different
#       2 for funny cases (can't stat, etc.)
#
def _cmp(a, b, sh, abs=abs, cmp=cmp):
    try:
        return not abs(cmp(a, b, sh))
    except os.error:
        return 2


# Return a copy with items that occur in skip removed.
#
def _filter(flist, skip):
    return list(ifilterfalse(skip.__contains__, flist))


# Demonstration and testing.
#
def demo():
    import sys
    import getopt
    options, args = getopt.getopt(sys.argv[1:], 'r')
    if len(args) != 2:
        raise getopt.GetoptError('need exactly two args', None)
    dd = hivecmp(args[0], args[1])
    if ('-r', '') in options:
        dd.report_full_closure()
    else:
        dd.report()


# This is a demo function for hive diff
# This one uses test_hives folders

def demolocal():
    os.chdir('../test_hives/')
    d = hivecmp('hive1','hive2')
    d.report_full_closure_patch()
    d.dump_hive_diff()

if __name__ == '__main__':
    demo()