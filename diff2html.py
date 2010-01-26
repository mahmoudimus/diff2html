#!/usr/bin/env python
# -*- coding: utf-8 -*-
__copyright__ = """
Copyright (C) 2001 Yves Bailly <diff2html@tuxfamily.org>
          (C) 2001 MandrakeSoft S.A.
          (C) 2010 Mahmoud Abdelkader <mahmoud@linux.com>

This script is free software; you can redistribute it and/or
modify it under the terms of the GNU Library General Public
License as published by the Free Software Foundation; either
version 2 of the License, or (at your option) any later version.

This script is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
Library General Public License for more details.

You should have received a copy of the GNU Library General Public
License along with this library; if not, write to the
Free Software Foundation, Inc., 59 Temple Place - Suite 330,
Boston, MA 02111-1307, USA, or look at the website
http://www.gnu.org/copyleft/gpl.html
"""

import sys
import os
import re
import time
import stat
import subprocess
import tempfile
from optparse import OptionParser
from optparse import IndentedHelpFormatter
from optparse import Option
from optparse import BadOptionError
from textwrap import dedent

default_css = \
"""
TABLE { border-collapse: collapse; border-spacing: 0px; }
TD.linenum { color: #909090;
             text-align: right;
             vertical-align: top;
             font-weight: bold;
             border-right: 1px solid black;
             border-left: 1px solid black; }
TD.added { background-color: #DDDDFF; }
TD.modified { background-color: #BBFFBB; }
TD.removed { background-color: #FFCCCC; }
TD.normal { background-color: #FFFFE1; }
"""


class HelpDesc(IndentedHelpFormatter):

    def _format_text(self, text):
        """Don't reformat the fucking text"""
        return text


class DiffOptionParser(OptionParser):

    def _process_args(self, largs, rargs, values):
        """_process_args(largs : [string],
                         rargs : [string],
                         values : Values)

        Process command-line arguments and populate 'values', consuming
        options and arguments from 'rargs'.  If 'allow_interspersed_args' is
        false, stop at the first non-option argument.  If true, accumulate any
        interspersed non-option arguments in 'largs'.
        """
        _optlist = [o.get_opt_string() for o in self._get_all_options()]
        if "--help" in _optlist:
            _optlist.append('-h')

        while rargs:
            arg = rargs[0]
            if not any(arg.startswith(e) for e in _optlist):
                if self.allow_interspersed_args:
                    largs.append(arg)
                    del rargs[0]
                    continue
            # We handle bare "--" explicitly, and bare "-" is handled by the
            # standard arg handler since the short arg case ensures that the
            # len of the opt string is greater than 1.
            if arg == "--":
                del rargs[0]
                return
            elif arg[0:2] == "--":
                # process a single long option (possibly with value(s))
                self._process_long_opt(rargs, values)
            elif arg[:1] == "-" and len(arg) > 1:
                # process a cluster of short options (possibly with
                # value(s) for the last one only)
                self._process_short_opts(rargs, values)
            elif self.allow_interspersed_args:
                largs.append(arg)
                del rargs[0]
            else:
                return                  # stop now, leave this arg in rarg


def _get_option_parser():
    usage = "%prog [options] file1 file2"
    desc = """\
           Formats diff(1) output to an HTML page on stdout
           Originally developed by:  Yves Bailly <diff2html@tuxfamily.org>
                                     http://diff2html.tuxfamily.org
           Updated and modified by:  Mahmoud Abdelkader <mahmoud@linux.com>
                                     http://mahmoudimus.com
           """
    epilogue = """\
           NOTE 1: if you give invalid additional options to diff(1),
                   diff2html will silently ignore this, but the resulting HTML
                   page will be incorrect;
           NOTE 2: for now, diff2html can't be used with standard input, so
                   the diff(1) '-' option can't be used.

           Usage Examples:
           # Basic use
           %(prog)s file1.txt file2.txt > differences.html

           # Treat all files as text and compare  them  line-by-line, even if
           # they do not seem to be text.
           %(prog)s -a file1 file2 > diffs.html

           # The same, but use the alternate style sheet contained in
           # diff_style.css
           diff2html --style-sheet diff_style.css -a file1 file2 > diffs.html

           The default, hard-coded style sheet is the following:
           %(default_css)s


           diff2html is released under the GNU GPL.
           Feel free to submit bugs or ideas to <diff2html@tuxfamily.org> or
           <mahmoud@linux.com>.
           """
    desc = dedent(desc)
    epilogue = dedent(epilogue) % {"prog": os.path.basename(sys.argv[0]),
                                   "default_css": default_css}
    parser = DiffOptionParser(usage=usage,
                              description=desc,
                              formatter=HelpDesc(),
                              epilog=epilogue)
    parser.add_option("--only-changes", action="store_true",
                     help="Do not display lines that have not changed")
    parser.add_option("--style-sheet",
                      help="Use an alternate style sheet, linked to the "
                           "given file")
    parser.add_option("--embeddable", action="store_true",
                      help="Allow diff colorizaton only such that it can be"
                           "embeddable")

    return parser


def str2html(s):
    s1 = s.replace(s.rstrip(), "&", "&amp;")
    if not s1:
        return s1
    s1 = s1.replace(s1, "<", "&lt;")
    s1 = s1.replace(s1, ">", "&gt;")
    # uhh, i'll come back to this monstrosity later
    i = 0
    s2 = ""
    while s1[i] == " ":
        s2 += "&nbsp;"
        i += 1
    s2 += s1[i:]
    return s2


def str_differ(arglist, options):
    diffstr_first, diffstr_second = arglist[-2:]
    tmp_file1 = tempfile.NamedTemporaryFile()
    tmp_file2 = tempfile.NamedTemporaryFile()
    tmp_file1.write(diffstr_first)
    tmp_file2.write(diffstr_second)
    tmp_file1.flush()
    tmp_file2.flush()
    results = file_differ(arglist[:-2] + [tmp_file1.name, tmp_file2.name],
                          options)
    tmp_file1.close()
    tmp_file2.close()
    return results


class DiffException(Exception):
    pass


def file_differ(arglist, options):
    """Options can be anything such that getattr(options, option) works"""
    args = ["diff"] + arglist
    # invoke diff
    diff = subprocess.Popen(args, stdout=subprocess.PIPE)
    stdout, stderr = diff.communicate()
    if stderr:
        raise DiffException(stderr)
    # stdout here should be good to go
    # let's get some statistics
    changed = {}
    deleted = {}
    added = {}
    # Magic regular expression
    diff_re = re.compile(
        r"^(?P<f1_start>\d+)(,(?P<f1_end>\d+))?" + \
         "(?P<diff>[acd])" + \
         "(?P<f2_start>\d+)(,(?P<f2_end>\d+))?")

    print type(stdout)


if __name__ == '__main__':
    parser = _get_option_parser()
    options, args = parser.parse_args()
    if not all([os.path.exists(args[-1]), os.path.exists(args[-2])]):
        raise IOError("Files %s do not exist or there's no read permissions, "
                      "aborting" % " or ".join(args[-2:]))
    print file_differ(args, options)
    print str_differ(["milo.com", "tozfeek"], options)

#if ( __name__ == "__main__" ) :


    ## Invokes "diff"
    #diff_stdout = os.popen("diff %s" % string.join(argv[1:]), "r")
    #diff_output = diff_stdout.readlines()
    #diff_stdout.close()
    ## Maps to store the reported differences
    #changed = {}
    #deleted = {}
    #added = {}
    ## Magic regular expression
    #diff_re = re.compile(
        #r"^(?P<f1_start>\d+)(,(?P<f1_end>\d+))?"+ \
         #"(?P<diff>[acd])"+ \
         #"(?P<f2_start>\d+)(,(?P<f2_end>\d+))?")
    ## Now parse the output from "diff"
    #for diff_line in diff_output:
        #diffs = diff_re.match(string.strip(diff_line))
        ## If the line doesn't match, it's useless for us
        #if not ( diffs  == None ) :
            ## Retrieving informations about the differences : 
            ## starting and ending lines (may be the same)
            #f1_start = int(diffs.group("f1_start"))
            #if ( diffs.group("f1_end") == None ) :
                #f1_end = f1_start
            #else :
                #f1_end = int(diffs.group("f1_end"))
            #f2_start = int(diffs.group("f2_start"))
            #if ( diffs.group("f2_end") == None ) :
                #f2_end = f2_start
            #else :
                #f2_end = int(diffs.group("f2_end"))
            #f1_nb = (f1_end - f1_start) + 1
            #f2_nb = (f2_end - f2_start) + 1
            ## Is it a changed (modified) line ?
            #if ( diffs.group("diff") == "c" ) :
                ## We have to handle the way "diff" reports lines merged
                ## or splitted
                #if ( f2_nb < f1_nb ) :
                    ## Lines merged : missing lines are marqued "deleted"
                    #for lf1 in range(f1_start, f1_start+f2_nb) :
                        #changed[lf1] = 0
                    #for lf1 in range(f1_start+f2_nb, f1_end+1) :
                        #deleted[lf1] = 0
                #elif ( f1_nb < f2_nb ) :
                    ## Lines splitted : extra lines are marqued "added"
                    #for lf1 in range(f1_start, f1_end+1) :
                        #changed[lf1] = 0
                    #for lf2 in range(f2_start+f1_nb, f2_end+1) :
                        #added[lf2] = 0
                #else :
                    ## Lines simply modified !
                    #for lf1 in range(f1_start, f1_end+1) :
                        #changed[lf1] = 0
            ## Is it an added line ?
            #elif ( diffs.group("diff") == "a" ) :
                #for lf2 in range(f2_start, f2_end+1):
                    #added[lf2] = 0
            #else :
            ## OK, so it's a deleted line
                #for lf1 in range(f1_start, f1_end+1) :
                    #deleted[lf1] = 0

    ## Storing the two compared files, to produce the HTML output
    #f1 = open(file1, "r")
    #f1_lines = f1.readlines()
    #f1.close()
    #f2 = open(file2, "r")
    #f2_lines = f2.readlines()
    #f2.close()

    ## Finding some infos about the files
    #f1_stat = os.stat(file1)
    #f2_stat = os.stat(file2)

    ## Printing the HTML header, and various known informations

    ## Preparing the links to changes
    #if ( len(changed) == 0 ) :
        #changed_lnks = "None"
    #else :
        #changed_lnks = ""
        #keys = changed.keys()
        #keys.sort()
        #for key in keys :
            #changed_lnks += "<a href=\"#F1_%d\">%d</a>, " % (key, key)
        #changed_lnks = changed_lnks[:-2]

    #if ( len(added) == 0 ) :
        #added_lnks = "None"
    #else :
        #added_lnks = ""
        #keys = added.keys()
        #keys.sort()
        #for key in keys :
            #added_lnks += "<a href=\"#F2_%d\">%d</a>, " % (key, key)
        #added_lnks = added_lnks[:-2]

    #if ( len(deleted) == 0 ) :
        #deleted_lnks = "None"
    #else :
        #deleted_lnks = ""
        #keys = deleted.keys()
        #keys.sort()
        #for key in keys :
            #deleted_lnks += "<a href=\"#F1_%d\">%d</a>, " % (key, key)
        #deleted_lnks = deleted_lnks[:-2]

    #print """
#<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN"
 #"http://www.w3.org/TR/REC-html40/loose.dtd">
#<html>
#<head>
    #<title>Differences between %s and %s</title>""" % (file1, file2)
    #if ( external_css == "" ) :
        #print "    <style>%s</style>" % default_css
    #else :
        #print "    <link rel=\"stylesheet\" href=\"%s\" type=\"text/css\">" % \
        #external_css

    #print """
#</head>
#<body>
#<table>
#<tr><td width="50%%">
#<table>
    #<tr>
        #<td class="modified">Modified lines:&nbsp;</td>
        #<td class="modified">%s</td>
    #</tr>
    #<tr>
        #<td class="added">Added line:&nbsp;</td>
        #<td class="added">%s</td>
    #</tr>
    #<tr>
        #<td class="removed">Removed line:&nbsp;</td>
        #<td class="removed">%s</td>
    #</tr>
#</table>
#</td>
#<td width="50%%">
#<i>Generated by <a href="http://diff2html.tuxfamily.org"><b>diff2html</b></a><br/>
#&copy; Yves Bailly, MandrakeSoft S.A. 2001<br/>
#<b>diff2html</b> is licensed under the <a
#href="http://www.gnu.org/copyleft/gpl.html">GNU GPL</a>.</i>
#</td></tr>
#</table>
#<hr/>
#<table>
    #<tr>
        #<th>&nbsp;</th>
        #<th width="45%%"><strong><big>%s</big></strong></th>
        #<th>&nbsp;</th>
        #<th>&nbsp;</th>
        #<th width="45%%"><strong><big>%s</big></strong></th>
    #</tr>
    #<tr>
        #<td width="16">&nbsp;</td>
        #<td>
        #%d lines<br/>
        #%d bytes<br/>
        #Last modified : %s<br/>
        #<hr/>
        #</td>
        #<td width="16">&nbsp;</td>
        #<td width="16">&nbsp;</td>
        #<td>
        #%d lines<br/>
        #%d bytes<br/>
        #Last modified : %s<br/>
        #<hr/>
        #</td>
    #</tr>
#""" % (changed_lnks, added_lnks, deleted_lnks,
       #file1, file2,
       #len(f1_lines), f1_stat[stat.ST_SIZE], 
       #time.asctime(time.gmtime(f1_stat[stat.ST_MTIME])),
       #len(f2_lines), f2_stat[stat.ST_SIZE], 
       #time.asctime(time.gmtime(f2_stat[stat.ST_MTIME])))
    
    ## Running through the differences...
    #nl1 = nl2 = 0
    #while not ( (nl1 >= len(f1_lines)) and (nl2 >= len(f2_lines)) ) :
        #if ( added.has_key(nl2+1) ) :
            #f2_lines[nl2]
      ## This is an added line
            #print """
    #<tr>
        #<td class="linenum">&nbsp;</td>
        #<td class="added">&nbsp;</td>
        #<td width="16">&nbsp;</td>
        #<td class="linenum"><a name="F2_%d">%d</a></td>
        #<td class="added">%s</td>
    #</tr>
#""" % (nl2+1, nl2+1, str2html(f2_lines[nl2]))
            #nl2 += 1
        #elif ( deleted.has_key(nl1+1) ) :
      ## This is a deleted line
            #print """
    #<tr>
        #<td class="linenum"><a name="F1_%d">%d</a></td>
        #<td class="removed">%s</td>
        #<td width="16">&nbsp;</td>
        #<td class="linenum">&nbsp;</td>
        #<td class="removed">&nbsp;</td>
    #</tr>
#""" % (nl1+1, nl1+1, str2html(f1_lines[nl1]))
            #nl1 += 1
        #elif ( changed.has_key(nl1+1) ) :
      ## This is a changed (modified) line
            #print """
    #<tr>
        #<td class="linenum"><a name="F1_%d">%d</a></td>
        #<td class="modified">%s</td>
        #<td width="16">&nbsp;</td>
        #<td class="linenum">%d</td>
        #<td class="modified">%s</td>
    #</tr>
#""" % (nl1+1, nl1+1, str2html(f1_lines[nl1]),
       #nl2+1, str2html(f2_lines[nl2]))
            #nl1 += 1
            #nl2 += 1
        #else :
      ## These lines have nothing special
            #if ( not only_changes ) :
                #print """
    #<tr>
        #<td class="linenum">%d</td>
        #<td class="normal">%s</td>
        #<td width="16">&nbsp;</td>
        #<td class="linenum">%d</td>
        #<td class="normal">%s</td>
    #</tr>
#""" % (nl1+1, str2html(f1_lines[nl1]),
       #nl2+1, str2html(f2_lines[nl2]))
            #nl1 += 1
            #nl2 += 1

    ## And finally, the end of the HTML
    #print """
#</table>
#<hr/>
#<i>Generated by <b>diff2html</b> on %s<br/>
#Command-line:</i> <tt>%s</tt>

#</body>
#</html>
#""" % (time.asctime(time.gmtime(time.time())), cmd_line)
