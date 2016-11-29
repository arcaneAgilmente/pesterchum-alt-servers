import re
import random
import ostools
import collections
from copy import copy
from datetime import timedelta
from PyQt4 import QtGui, QtCore

from generic import mysteryTime
from quirks import ScriptQuirks
from pyquirks import PythonQuirks
from luaquirks import LuaQuirks

# karxi: My own contribution to this - a proper lexer.
import pnc.lexercon as lexercon

# I'll clean up the things that are no longer needed once the transition is
# actually finished.
_ctag_begin = re.compile(r'(?i)<c=(.*?)>')
_gtag_begin = re.compile(r'(?i)<g[a-f]>')
_ctag_end = re.compile(r'(?i)</c>')
_ctag_rgb = re.compile(r'\d+,\d+,\d+')
_urlre = re.compile(r"(?i)(?:^|(?<=\s))(?:(?:https?|ftp)://|magnet:)[^\s]+")
_url2re = re.compile(r"(?i)(?<!//)\bwww\.[^\s]+?\.")
_memore = re.compile(r"(\s|^)(#[A-Za-z0-9_]+)")
_handlere = re.compile(r"(\s|^)(@[A-Za-z0-9_]+)")
_imgre = re.compile(r"""(?i)<img src=['"](\S+)['"]\s*/>""")
_mecmdre = re.compile(r"^(/me|PESTERCHUM:ME)(\S*)")
_oocre = re.compile(r"([\[(\{])\1.*([\])\}])\2")
_format_begin = re.compile(r'(?i)<([ibu])>')
_format_end = re.compile(r'(?i)</([ibu])>')
_honk = re.compile(r"(?i)\bhonk\b")

quirkloader = ScriptQuirks()
quirkloader.add(PythonQuirks())
quirkloader.add(LuaQuirks())
quirkloader.loadAll()
print quirkloader.funcre()
_functionre = re.compile(r"%s" % quirkloader.funcre())
_groupre = re.compile(r"\\([0-9]+)")

def reloadQuirkFunctions():
    quirkloader.loadAll()
    global _functionre
    _functionre = re.compile(r"%s" % quirkloader.funcre())

def lexer(string, objlist):
    """objlist is a list: [(objecttype, re),...] list is in order of preference"""
    stringlist = [string]
    for (oType, regexp) in objlist:
        newstringlist = []
        for (stri, s) in enumerate(stringlist):
            if type(s) not in [str, unicode]:
                newstringlist.append(s)
                continue
            lasti = 0
            for m in regexp.finditer(s):
                start = m.start()
                end = m.end()
                tag = oType(m.group(0), *m.groups())
                if lasti != start:
                    newstringlist.append(s[lasti:start])
                newstringlist.append(tag)
                lasti = end
            if lasti < len(string):
                newstringlist.append(s[lasti:])
        stringlist = copy(newstringlist)
    return stringlist

# karxi: All of these were derived from object before. I changed them to
# lexercon.Chunk so that I'd have an easier way to match against them until
# they're redone/removed.
class colorBegin(lexercon.Chunk):
    def __init__(self, string, color):
        self.string = string
        self.color = color
    def convert(self, format):
        color = self.color
        if format == "text":
            return ""
        if _ctag_rgb.match(color) is not None:
            if format=='ctag':
                return "<c=%s>" % (color)
            try:
                qc = QtGui.QColor(*[int(c) for c in color.split(",")])
            except ValueError:
                qc = QtGui.QColor("black")
        else:
            qc = QtGui.QColor(color)
        if not qc.isValid():
            qc = QtGui.QColor("black")
        if format == "html":
            return '<span style="color:%s">' % (qc.name())
        elif format == "bbcode":
            return '[color=%s]' % (qc.name())
        elif format == "ctag":
            (r,g,b,a) = qc.getRgb()
            return '<c=%s,%s,%s>' % (r,g,b)

class colorEnd(lexercon.Chunk):
    def __init__(self, string):
        self.string = string
    def convert(self, format):
        if format == "html":
            return "</span>"
        elif format == "bbcode":
            return "[/color]"
        elif format == "text":
            return ""
        else:
            return self.string

class formatBegin(lexercon.Chunk):
    def __init__(self, string, ftype):
        self.string = string
        self.ftype = ftype
    def convert(self, format):
        if format == "html":
            return "<%s>" % (self.ftype)
        elif format == "bbcode":
            return "[%s]" % (self.ftype)
        elif format == "text":
            return ""
        else:
            return self.string

class formatEnd(lexercon.Chunk):
    def __init__(self, string, ftype):
        self.string = string
        self.ftype = ftype
    def convert(self, format):
        if format == "html":
            return "</%s>" % (self.ftype)
        elif format == "bbcode":
            return "[/%s]" % (self.ftype)
        elif format == "text":
            return ""
        else:
            return self.string

class hyperlink(lexercon.Chunk):
    def __init__(self, string):
        self.string = string
    def convert(self, format):
        if format == "html":
            return "<a href='%s'>%s</a>" % (self.string, self.string)
        elif format == "bbcode":
            return "[url]%s[/url]" % (self.string)
        else:
            return self.string

class hyperlink_lazy(hyperlink):
    def __init__(self, string):
        self.string = "http://" + string

class imagelink(lexercon.Chunk):
    def __init__(self, string, img):
        self.string = string
        self.img = img
    def convert(self, format):
        if format == "html":
            return self.string
        elif format == "bbcode":
            if self.img[0:7] == "http://":
                return "[img]%s[/img]" % (self.img)
            else:
                return ""
        else:
            return ""

class memolex(lexercon.Chunk):
    def __init__(self, string, space, channel):
        self.string = string
        self.space = space
        self.channel = channel
    def convert(self, format):
        if format == "html":
            return "%s<a href='%s'>%s</a>" % (self.space, self.channel, self.channel)
        else:
            return self.string

class chumhandlelex(lexercon.Chunk):
    def __init__(self, string, space, handle):
        self.string = string
        self.space = space
        self.handle = handle
    def convert(self, format):
        if format == "html":
            return "%s<a href='%s'>%s</a>" % (self.space, self.handle, self.handle)
        else:
            return self.string

class smiley(lexercon.Chunk):
    def __init__(self, string):
        self.string = string
    def convert(self, format):
        if format == "html":
            return "<img src='smilies/%s' alt='%s' title='%s' />" % (smiledict[self.string], self.string, self.string)
        else:
            return self.string

class honker(lexercon.Chunk):
    def __init__(self, string):
        self.string = string
    def convert(self, format):
        if format == "html":
            return "<img src='smilies/honk.png' alt'honk' title='honk' />"
        else:
            return self.string

class mecmd(lexercon.Chunk):
    def __init__(self, string, mecmd, suffix):
        self.string = string
        self.suffix = suffix
    def convert(self, format):
        return self.string

kxpclexer = lexercon.Pesterchum()

def kxlexMsg(string):
    # Do a bit of sanitization.
    msg = unicode(string)
    # TODO: Let people paste line-by-line normally.
    msg = msg.replace('\n', ' ').replace('\r', ' ')
    # Something the original doesn't seem to have accounted for.
    # Replace tabs with 4 spaces.
    msg = msg.replace('\t', ' ' * 4)
    # Begin lexing.
    msg = kxpclexer.lex(msg)
    # ...and that's it for this.
    return msg

def lexMessage(string):
    lexlist = [(mecmd, _mecmdre),
               (colorBegin, _ctag_begin), (colorBegin, _gtag_begin),
               (colorEnd, _ctag_end),
               # karxi: Disabled this for now. No common versions of Pesterchum
               # actually use it, save for Chumdroid...which shouldn't.
               # When I change out parsers, I might add it back in.
               ##(formatBegin, _format_begin), (formatEnd, _format_end),
               (imagelink, _imgre),
               (hyperlink, _urlre), (hyperlink_lazy, _url2re),
               (memolex, _memore),
               (chumhandlelex, _handlere),
               (smiley, _smilere),
               (honker, _honk)]

    string = unicode(string)
    string = string.replace("\n", " ").replace("\r", " ")
    lexed = lexer(unicode(string), lexlist)

    balanced = []
    beginc = 0
    endc = 0
    for o in lexed:
        if type(o) is colorBegin:
            beginc += 1
            balanced.append(o)
        elif type(o) is colorEnd:
            if beginc >= endc:
                endc += 1
                balanced.append(o)
            else:
                balanced.append(o.string)
        else:
            balanced.append(o)
    if beginc > endc:
        for i in range(0, beginc-endc):
            balanced.append(colorEnd("</c>"))
    if len(balanced) == 0:
        balanced.append("")
    if type(balanced[len(balanced)-1]) not in [str, unicode]:
        balanced.append("")
    return balanced

def convertTags(lexed, format="html"):
    if format not in ["html", "bbcode", "ctag", "text"]:
        raise ValueError("Color format not recognized")

    if type(lexed) in [str, unicode]:
        lexed = lexMessage(lexed)
    escaped = ""
    firststr = True
    for (i, o) in enumerate(lexed):
        if type(o) in [str, unicode]:
            if format == "html":
                escaped += o.replace("&", "&amp;").replace(">", "&gt;").replace("<","&lt;")
            else:
                escaped += o
        else:
            escaped += o.convert(format)

    return escaped

def _max_msg_len(mask=None, target=None):
    # karxi: Copied from another file of mine, and modified to work with
    # Pesterchum.
    # Note that this effectively assumes the worst when not provided the
    # information it needs to get an accurate read, so later on, it'll need to
    # be given a nick or the user's hostmask, as well as where the message is
    # being sent.
    # It effectively has to construct the message that'll be sent in advance.
    limit = 512

    # Start subtracting
    # ':', " PRIVMSG ", ' ', ':', \r\n
    limit -= 14

    if mask is not None:
        # Since this will be included in what we send
        limit -= len(str(mask))
    else:
        # Since we should always be able to fetch this
        # karxi: ... Which we can't, right now, unlike in the old script.
        # TODO: Resolve this issue, give it the necessary information.
        nick = None
        # If we CAN'T, stick with a length of 30, since that seems to be
        # the average maximum nowadays
        limit -= len(nick) if nick is not None else 30
        # '!', '@'
        limit -= 2
        # Maximum ident length
        limit -= 10
        # Maximum (?) host length
        limit -= 63				# RFC 2812
    # The target is the place this is getting sent to - a channel or a nick
    if target is not None:
        limit -= len(target)
    else:
        # Normally I'd assume about 60...just to be safe.
        # However, the current (2016-11-13) Pesterchum limit for memo name
        # length is 32, so I'll bump it to 40 for some built-in leeway.
        limit -= 40

    return limit

def kxsplitMsg(lexed, fmt="pchum", maxlen=None, debug=False):
    """Split messages so that they don't go over the length limit.
    Returns a list of the messages, neatly split.
    
    Keep in mind that there's a little bit of magic involved in this at the
    moment; some unsafe assumptions are made."""
    # Procedure: Lex. Convert for lengths as we go, keep starting tag
    # length as we go too. Split whenever we hit the limit, add the tags to
    # the start of the next line (or just keep a running line length
    # total), and continue.
    # N.B.: Keep the end tag length too. (+4 for each.)
    # Copy the list so we can't break anything.
    lexed = list(lexed)
    working = []
    output = []
    open_ctags = []
    # Number of characters we've used.
    curlen = 0
    # Maximum number of characters *to* use.
    if not maxlen:
        maxlen = _max_msg_len()
    elif maxlen < 0:
        # Subtract the (negative) length, giving us less leeway in this
        # function.
        maxlen = _max_msg_len() + maxlen

    # Defined here, but modified in the loop.
    msglen = 0

    def efflenleft():
        """Get the remaining space we have to work with, accounting for closing
        tags that will be needed."""
        return maxlen - curlen - (len(open_ctags) * 4)

    safekeeping = lexed[:]
    lexed = collections.deque(lexed)
    rounds = 0
    while len(lexed) > 0:
        rounds += 1
        if debug:
            print "[Starting round {}...]".format(rounds)
        msg = lexed.popleft()
        msglen = 0
        is_text = False
        text_preproc = False

        try:
            msglen = len(msg.convert(fmt))
        except AttributeError:
            # It's probably not a lexer tag. Assume a string.
            # The input to this is supposed to be sanitary, after all.
            msglen = len(msg)
            # We allow this to error out if it fails for some reason.
            # Remind us that it's a string, and thus can be split.
            is_text = True

        # Test if we have room.
        if msglen > efflenleft():
            # We do NOT have room - which means we need to think of how to
            # handle this.
            # If we have text, we can split it, keeping color codes in mind.
            # Since those were already parsed, we don't have to worry about
            # breaking something that way.
            # Thus, we can split it, finalize it, and add the remainder to the
            # next line (after the color codes).
            if is_text and efflenleft() > 30:
                text_preproc = True
                # We use 30 as a general 'guess' - if there's less space than
                # that, it's probably not worth trying to cram text in.
                # This also saves us from infinitely trying to reduce the size
                # of the input.
                stack = []
                # We have text to split.
                # This is okay because we don't apply the changes until the
                # end - and the rest is shoved onto the stack to be dealt with
                # immediately after.
                lenl = efflenleft()
                subround = 0
                while len(msg) > lenl:
                    subround += 1
                    if debug:
                        print "[Splitting round {}-{}...]".format(
                                rounds, subround
                                )
                    point = msg.rfind(' ', 0, lenl)
                    if point < 0:
                        # No spaces to break on...ugh. Break at the last space
                        # we can instead.
                        point = lenl ## - 1
                        # NOTE: The - 1 is for safety (but probably isn't
                        # actually necessary.)
                    # Split and push what we have.
                    stack.append(msg[:point])
                    # Remove what we just added.
                    msg = msg[point:]
                    if debug:
                        print "msg = {!r}".format(msg)
                else:
                    # Catch the remainder.
                    stack.append(msg)
                    if debug:
                        print "msg caught; stack = {!r}".format(stack)
                # Done processing. Pluck out the first portion so we can
                # continue processing, then add the rest to our waiting list.
                msg = stack.pop(0)
                msglen = len(msg)
                # Now we have a separated list, so we can add it.
                # First we have to reverse it, because the extendleft method of
                # deque objects - like our lexed queue - inserts the elements
                # *backwards*....
                stack.reverse()
                # Now we put them on 'top' of the proverbial deck, and deal
                # with them next round.
                lexed.extendleft(stack)
                # We'll deal with those later. Now to get the 'msg' on the
                # working list and finalize it for output - which really just
                # means forcing the issue....
                working.append(msg)
                curlen += msglen

            # Clear the slate. Add the remaining ctags, then add working to
            # output, then clear working and statistics. Then we can move on to
            # append as normal.
            # Keep in mind that any open ctags get added to the beginning of
            # working again, since they're still open!

            # ...
            # ON SECOND THOUGHT: The lexer balances for us, so let's just use
            # that for now. I can split up the function for this later.
            working = u''.join(kxpclexer.list_convert(working))
            working = kxpclexer.lex(working)
            working = u''.join(kxpclexer.list_convert(working))
            # TODO: Is that lazy? Yes. This is a modification made to test if
            # it'll work, *not* if it'll be efficient.

            # Now that it's done the work for us, append and resume.
            output.append(working)
            # Reset working, starting it with the unclosed ctags.
            working = open_ctags[:]
            # Calculate the length of the starting tags, add it before anything
            # else.
            curlen = sum(len(tag.convert(fmt)) for tag in working)
            if text_preproc:
                # If we got here, it means we overflowed due to text - which
                # means we also split and added it to working. There's no
                # reason to continue and add it twice.
                # This could be handled with an elif chain, but eh.
                continue
            # If we got here, it means we haven't done anything with 'msg' yet,
            # in spite of popping it from lexed, so add it back for the next
            # round.
            # This sends it through for another round of splitting and work,
            # possibly.
            lexed.appendleft(msg)
            continue

        # Normal tag processing stuff. Considerably less interesting/intensive
        # than the text processing we did up there.
        if isinstance(msg, lexercon.CTagEnd):
            # Check for Ends first (subclassing issue).
            if len(open_ctags) > 0:
                # Don't add it unless it's going to make things /more/ even.
                # We could have a Strict checker that errors on that, who
                # knows.
                # We just closed a ctag.
                open_ctags.pop()
            else:
                # Ignore it.
                # NOTE: I realize this is going to screw up something I do, but
                # it also stops us from screwing up Chumdroid, so...whatever.
                continue
        elif isinstance(msg, lexercon.CTag):
            # It's an opening color tag!
            open_ctags.append(msg)

        # Add it to the working message.
        working.append(msg)

        # Record the additional length.
        # Also, need to be sure to account for the ends that would be added.
        curlen += msglen
    else:
        # Once we're finally out of things to add, we're, well...out.
        # So add working to the result one last time.
        working = kxpclexer.list_convert(working)
        if len(working) > 0:
            working = u''.join(working)
            output.append(working)

    # We're...done?
    return output

def splitMessage(msg, format="ctag"):
    """Splits message if it is too long.
    This is the older version of this function, kept for compatibility.
    It will eventually be phased out."""
    # split long text lines
    buf = []
    for o in msg:
        if type(o) in [str, unicode] and len(o) > 200:
            # Split with a step of 200. I.e., cut long segments into chunks of
            # 200 characters.
            # I'm...not sure why this is done. I'll probably factor it out
            # later on.
            for i in range(0, len(o), 200):
                buf.append(o[i:i+200])
        else:
            # Add non-text tags or 'short' segments without processing.
            buf.append(o)
    # Copy the iterative variable.
    msg = list(buf)
    # This is the working segment.
    working = []
    # Keep a stack of open color tags.
    cbegintags = []
    # This is the final result.
    output = []
    print repr(msg)
    for o in msg:
        oldctag = None
        # Add to the working segment.
        working.append(o)
        if type(o) is colorBegin:
            # Track the open tag.
            cbegintags.append(o)
        elif type(o) is colorEnd:
            try:
                # Remove the last open tag, since we've closed it.
                oldctag = cbegintags.pop()
            except IndexError:
                pass
        # THIS part is the part I don't get. I'll revise it later....
        # It doesn't seem to catch ending ctags properly...or beginning ones.
        # It's pretty much just broken, likely due to the line below.
        # Maybe I can convert the tags, save the beginning tags, check their
        # lengths and apply them after a split - or even iterate over each set,
        # applying old tags before continuing...I don't know.
        # yeah normally i'd do binary search but im lazy
        # Get length of beginning tags, and the end tags that'd be applied.
        msglen = len(convertTags(working, format)) + 4*(len(cbegintags))
        # Previously this used 400.
        if msglen > _max_msg_len():
            working.pop()
            if type(o) is colorBegin:
                cbegintags.pop()
            elif type(o) is colorEnd and oldctag is not None:
                cbegintags.append(oldctag)
            if len(working) == 0:
                output.append([o])
            else:
                tmp = []
                for color in cbegintags:
                    working.append(colorEnd("</c>"))
                    tmp.append(color)
                output.append(working)
                if type(o) is colorBegin:
                    cbegintags.append(o)
                elif type(o) is colorEnd:
                    try:
                        cbegintags.pop()
                    except IndexError:
                        pass
                tmp.append(o)
                working = tmp

    if len(working) > 0:
        # Add any stragglers.
        output.append(working)
    return output

def _is_ooc(msg, strict=True):
    """Check if a line is OOC. Note that Pesterchum *is* kind enough to strip
    trailing spaces for us, even in the older versions, but we don't do that in
    this function. (It's handled by the calling one.)"""
    # Define the matching braces.
    braces = (
            ('(', ')'),
            ('[', ']'),
            ('{', '}')
            )

    oocDetected = _oocre.match(msg)
    # Somewhat-improved matching.
    if oocDetected:
        if not strict:
            # The regex matched and we're supposed to be lazy. We're done here.
            return True
        # We have a match....
        ooc1, ooc2 = oocDetected.group(1, 2)
        # Make sure the appropriate braces are used.
        mbraces = map(
                lambda br: ooc1 == br[0] and ooc2 == br[1],
                braces)
        if any(mbraces):
            # If any of those passes matched, we're good to go; it's OOC.
            return True
    return False

def kxhandleInput(ctx, text=None, flavor=None):
    """The function that user input that should be sent to the server is routed
    through. Handles lexing, splitting, and quirk application."""
    # Flavor is important for logic, ctx is 'self'.
    # Flavors are 'convo', 'menus', and 'memos' - so named after the source
    # files for the original sentMessage variants.

    if flavor is None:
        return ValueError("A flavor is needed to determine suitable logic!")

    if text is None:
        # Fetch the raw text from the input box.
        text = ctx.textInput.text()
        text = unicode(ctx.textInput.text())

    # Preprocessing stuff.
    msg = text.strip()
    if msg == "" or msg.startswith("PESTERCHUM:"):
        # We don't allow users to send system messages. There's also no
        # point if they haven't entered anything.
        return

    # Add the *raw* text to our history.
    ctx.history.add(text)

    oocDetected = _is_ooc(msg, strict=True)

    if flavor != "menus":
        # Determine if we should be OOC.
        is_ooc = ctx.ooc or oocDetected
        # Determine if the line actually *is* OOC.
        if is_ooc and not oocDetected:
            # If we're supposed to be OOC, apply it artificially.
            msg = u"(( {} ))".format(msg)
        # Also, quirk stuff.
        should_quirk = ctx.applyquirks
    else:
        # 'menus' means a quirk tester window, which doesn't have an OOC
        # variable, so we assume it's not OOC.
        # It also invariably has quirks enabled, so there's no setting for
        # that.
        is_ooc = False
        should_quirk = True

    # I'm pretty sure that putting a space before a /me *should* break the
    # /me, but in practice, that's not the case.
    is_action = msg.startswith("/me")
    
    # Begin message processing.
    # We use 'text' despite its lack of processing because it's simpler.
    if should_quirk and not (is_action or is_ooc):
        # Fetch the quirks we'll have to apply.
        quirks = ctx.mainwindow.userprofile.quirks
        try:
            # Do quirk things. (Ugly, but it'll have to do for now.)
            # TODO: Look into the quirk system, modify/redo it.
            # Gotta encapsulate or we might parse the wrong way.
            msg = quirks.apply([msg])
        except Exception as err:
            # Tell the user we couldn't do quirk things.
            # TODO: Include the actual error...and the quirk it came from?
            msgbox = QtGui.QMessageBox()
            msgbox.setText("Whoa there! There seems to be a problem.")
            err_info = "A quirk seems to be having a problem. (Error: {!s})"
            err_info = err_info.format(err)
            msgbox.setInformativeText(err_info)
            msgbox.exec_()
            return
        
    # Debug output.
    print msg
    # karxi: We have a list...but I'm not sure if we ever get anything else, so
    # best to play it safe. I may remove this during later refactoring.
    if isinstance(msg, list):
        for i, m in enumerate(msg):
            if isinstance(m, lexercon.Chunk):
                # NOTE: KLUDGE. Filters out old PChum objects.
                # karxi: This only works because I went in and subtyped them to
                # an object type I provided - just so I could pluck them out
                # later.
                msg[i] = m.convert(format="ctag")
        msg = u''.join(msg)

    # Quirks have been applied. Lex the messages (finally).
    msg = kxlexMsg(msg)

    # Remove coloring if this is a /me!
    if is_action:
        # Filter out formatting specifiers (just ctags, at the moment).
        msg = filter(
                lambda m: not isinstance(m,
                    (lexercon.CTag, lexercon.CTagEnd)
                    ),
                msg
                )
        # We'll also add /me to the beginning of any new messages, later.

    # Put what's necessary in before splitting.
    # Fetch our time if we're producing this for a memo.
    if flavor == "memos":
        if ctx.time.getTime() == None:
            ctx.sendtime()
        grammar = ctx.time.getGrammar()
        # Oh, great...there's a parsing error to work around. Times are added
        # automatically when received, but not when added directly?... I'll
        # have to unify that.
        # TODO: Fix parsing disparity.
        initials = ctx.mainwindow.profile().initials()
        colorcmd = ctx.mainwindow.profile().colorcmd()
        # We'll use those later.

    # Split the messages so we don't go over the buffer and lose text.
    maxlen = _max_msg_len()
    # Since we have to do some post-processing, we need to adjust the maximum
    # length we can use.
    if flavor == "convo":
        # The old Pesterchum setup used 200 for this.
        maxlen = 300
    elif flavor == "memos":
        # Use the max, with some room added so we can make additions.
        maxlen -= 20

    # Split the message. (Finally.)
    # This is also set up to parse it into strings.
    lexmsgs = kxsplitMsg(msg, "pchum", maxlen=maxlen)
    # Strip off the excess.
    for i, m in enumerate(lexmsgs):
        lexmsgs[i] = m.strip()

    # Pester message handling.
    if flavor == "convo":
        # if ceased, rebegin
        if hasattr(ctx, 'chumopen') and not ctx.chumopen:
            ctx.mainwindow.newConvoStarted.emit(
                    QtCore.QString(ctx.title()), True
                    )
            ctx.setChumOpen(True)

    # Post-process and send the messages.
    for i, lm in enumerate(lexmsgs):
        # If we're working with an action and we split, it should have /mes.
        if is_action and i > 0:
            # Add them post-split.
            lm = u"/me " + lm
            # NOTE: No reason to reassign for now, but...why not?
            lexmsgs[i] = lm

        # Copy the lexed result.
        # Note that memos have to separate processing here. The adds and sends
        # should be kept to the end because of that, near the emission.
        clientMsg = copy(lm)
        serverMsg = copy(lm)

        # Memo-specific processing.
        if flavor == "memos" and not is_action:
            # Quirks were already applied, so get the prefix/postfix stuff
            # ready.
            # We fetched the information outside of the loop, so just
            # construct the messages.

            clientMsg = u"<c={1}>{2}{3}{4}: {0}</c>".format(
                    clientMsg, colorcmd, grammar.pcf, initials, grammar.number
                    )
            # Not sure if this needs a space at the end...?
            serverMsg = u"<c={1}>{2}: {0}</c>".format(
                    serverMsg, colorcmd, initials)

        ctx.addMessage(clientMsg, True)
        if flavor != "menus":
            # If we're not doing quirk testing, actually send.
            ctx.messageSent.emit(serverMsg, ctx.title())

    # Clear the input.
    ctx.textInput.setText("")


def addTimeInitial(string, grammar):
    endofi = string.find(":")
    endoftag = string.find(">")
    # support Doc Scratch mode
    if (endoftag < 0 or endoftag > 16) or (endofi < 0 or endofi > 17):
        return string
    return string[0:endoftag+1]+grammar.pcf+string[endoftag+1:endofi]+grammar.number+string[endofi:]

def timeProtocol(cmd):
    dir = cmd[0]
    if dir == "?":
        return mysteryTime(0)
    cmd = cmd[1:]
    cmd = re.sub("[^0-9:]", "", cmd)
    try:
        l = [int(x) for x in cmd.split(":")]
    except ValueError:
        l = [0,0]
    timed = timedelta(0, l[0]*3600+l[1]*60)
    if dir == "P":
        timed = timed*-1
    return timed

def timeDifference(td):
    if type(td) is mysteryTime:
        return "??:?? FROM ????"
    if td < timedelta(0):
        when = "AGO"
    else:
        when = "FROM NOW"
    atd = abs(td)
    minutes = (atd.days*86400 + atd.seconds) // 60
    hours = minutes // 60
    leftoverminutes = minutes % 60
    if atd == timedelta(0):
        timetext = "RIGHT NOW"
    elif atd < timedelta(0,3600):
        if minutes == 1:
            timetext = "%d MINUTE %s" % (minutes, when)
        else:
            timetext = "%d MINUTES %s" % (minutes, when)
    elif atd < timedelta(0,3600*100):
        if hours == 1 and leftoverminutes == 0:
            timetext = "%d:%02d HOUR %s" % (hours, leftoverminutes, when)
        else:
            timetext = "%d:%02d HOURS %s" % (hours, leftoverminutes, when)
    else:
        timetext = "%d HOURS %s" % (hours, when)
    return timetext

def nonerep(text):
    return text

class parseLeaf(object):
    def __init__(self, function, parent):
        self.nodes = []
        self.function = function
        self.parent = parent
    def append(self, node):
        self.nodes.append(node)
    def expand(self, mo):
        out = ""
        for n in self.nodes:
            if type(n) == parseLeaf:
                out += n.expand(mo)
            elif type(n) == backreference:
                out += mo.group(int(n.number))
            else:
                out += n
        out = self.function(out)
        return out

class backreference(object):
    def __init__(self, number):
        self.number = number
    def __str__(self):
        return self.number

def parseRegexpFunctions(to):
    parsed = parseLeaf(nonerep, None)
    current = parsed
    curi = 0
    functiondict = quirkloader.quirks
    while curi < len(to):
        tmp = to[curi:]
        mo = _functionre.search(tmp)
        if mo is not None:
            if mo.start() > 0:
                current.append(to[curi:curi+mo.start()])
            backr = _groupre.search(mo.group())
            if backr is not None:
                current.append(backreference(backr.group(1)))
            elif mo.group()[:-1] in functiondict.keys():
                p = parseLeaf(functiondict[mo.group()[:-1]], current)
                current.append(p)
                current = p
            elif mo.group() == ")":
                if current.parent is not None:
                    current = current.parent
                else:
                    current.append(")")
            curi = mo.end()+curi
        else:
            current.append(to[curi:])
            curi = len(to)
    return parsed


def img2smiley(string):
    string = unicode(string)
    def imagerep(mo):
        return reverse_smiley[mo.group(1)]
    string = re.sub(r'<img src="smilies/(\S+)" />', imagerep, string)
    return string

smiledict = {
    ":rancorous:": "pc_rancorous.png",
    ":apple:": "apple.png",
    ":bathearst:": "bathearst.png",
    ":cathearst:": "cathearst.png",
    ":woeful:": "pc_bemused.png",
    ":sorrow:": "blacktear.png",
    ":pleasant:": "pc_pleasant.png",
    ":blueghost:": "blueslimer.gif",
    ":slimer:": "slimer.gif",
    ":candycorn:": "candycorn.png",
    ":cheer:": "cheer.gif",
    ":duhjohn:": "confusedjohn.gif",
    ":datrump:": "datrump.png",
    ":facepalm:": "facepalm.png",
    ":bonk:": "headbonk.gif",
    ":mspa:": "mspa_face.png",
    ":gun:": "mspa_reader.gif",
    ":cal:": "lilcal.png",
    ":amazedfirman:": "pc_amazedfirman.png",
    ":amazed:": "pc_amazed.png",
    ":chummy:": "pc_chummy.png",
    ":cool:": "pccool.png",
    ":smooth:": "pccool.png",
    ":distraughtfirman": "pc_distraughtfirman.png",
    ":distraught:": "pc_distraught.png",
    ":insolent:": "pc_insolent.png",
    ":bemused:": "pc_bemused.png",
    ":3:": "pckitty.png",
    ":mystified:": "pc_mystified.png",
    ":pranky:": "pc_pranky.png",
    ":tense:": "pc_tense.png",
    ":record:": "record.gif",
    ":squiddle:": "squiddle.gif",
    ":tab:": "tab.gif",
    ":beetip:": "theprofessor.png",
    ":flipout:": "weasel.gif",
    ":befuddled:": "what.png",
    ":pumpkin:": "whatpumpkin.png",
    ":trollcool:": "trollcool.png",
    ":jadecry:": "jadespritehead.gif",
    ":ecstatic:": "ecstatic.png",
    ":relaxed:": "relaxed.png",
    ":discontent:": "discontent.png",
    ":devious:": "devious.png",
    ":sleek:": "sleek.png",
    ":detestful:": "detestful.png",
    ":mirthful:": "mirthful.png",
    ":manipulative:": "manipulative.png",
    ":vigorous:": "vigorous.png",
    ":perky:": "perky.png",
    ":acceptant:": "acceptant.png",
    ":olliesouty:": "olliesouty.gif",
    ":billiards:": "poolballS.gif",
    ":billiardslarge:": "poolballL.gif",
    ":whatdidyoudo:": "whatdidyoudo.gif",
    ":brocool:": "pcstrider.png",
    ":trollbro:": "trollbro.png",
    ":playagame:": "saw.gif",
    ":trollc00l:": "trollc00l.gif",
    ":suckers:": "Suckers.gif",
    ":scorpio:": "scorpio.gif",
    ":shades:": "shades.png",
    }

if ostools.isOSXBundle():
    for emote in smiledict:
        graphic = smiledict[emote]
        if graphic.find(".gif"):
            graphic = graphic.replace(".gif", ".png")
            smiledict[emote] = graphic




reverse_smiley = dict((v,k) for k, v in smiledict.iteritems())
_smilere = re.compile("|".join(smiledict.keys()))

class ThemeException(Exception):
    def __init__(self, value):
        self.parameter = value
    def __str__(self):
        return repr(self.parameter)

def themeChecker(theme):
    needs = ["main/size", "main/icon", "main/windowtitle", "main/style", \
    "main/background-image", "main/menubar/style", "main/menu/menuitem", \
    "main/menu/style", "main/menu/selected", "main/close/image", \
    "main/close/loc", "main/minimize/image", "main/minimize/loc", \
    "main/menu/loc", "main/menus/client/logviewer", \
    "main/menus/client/addgroup", "main/menus/client/options", \
    "main/menus/client/exit", "main/menus/client/userlist", \
    "main/menus/client/memos", "main/menus/client/import", \
    "main/menus/client/idle", "main/menus/client/reconnect", \
    "main/menus/client/_name", "main/menus/profile/quirks", \
    "main/menus/profile/block", "main/menus/profile/color", \
    "main/menus/profile/switch", "main/menus/profile/_name", \
    "main/menus/help/about", "main/menus/help/_name", "main/moodlabel/text", \
    "main/moodlabel/loc", "main/moodlabel/style", "main/moods", \
    "main/addchum/style", "main/addchum/text", "main/addchum/size", \
    "main/addchum/loc", "main/pester/text", "main/pester/size", \
    "main/pester/loc", "main/block/text", "main/block/size", "main/block/loc", \
    "main/mychumhandle/label/text", "main/mychumhandle/label/loc", \
    "main/mychumhandle/label/style", "main/mychumhandle/handle/loc", \
    "main/mychumhandle/handle/size", "main/mychumhandle/handle/style", \
    "main/mychumhandle/colorswatch/size", "main/mychumhandle/colorswatch/loc", \
    "main/defaultmood", "main/chums/size", "main/chums/loc", \
    "main/chums/style", "main/menus/rclickchumlist/pester", \
    "main/menus/rclickchumlist/removechum", \
    "main/menus/rclickchumlist/blockchum", "main/menus/rclickchumlist/viewlog", \
    "main/menus/rclickchumlist/removegroup", \
    "main/menus/rclickchumlist/renamegroup", \
    "main/menus/rclickchumlist/movechum", "convo/size", \
    "convo/tabwindow/style", "convo/tabs/tabstyle", "convo/tabs/style", \
    "convo/tabs/selectedstyle", "convo/style", "convo/margins", \
    "convo/chumlabel/text", "convo/chumlabel/style", "convo/chumlabel/align/h", \
    "convo/chumlabel/align/v", "convo/chumlabel/maxheight", \
    "convo/chumlabel/minheight", "main/menus/rclickchumlist/quirksoff", \
    "main/menus/rclickchumlist/addchum", "main/menus/rclickchumlist/blockchum", \
    "main/menus/rclickchumlist/unblockchum", \
    "main/menus/rclickchumlist/viewlog", "main/trollslum/size", \
    "main/trollslum/style", "main/trollslum/label/text", \
    "main/trollslum/label/style", "main/menus/profile/block", \
    "main/chums/moods/blocked/icon", "convo/systemMsgColor", \
    "convo/textarea/style", "convo/text/beganpester", "convo/text/ceasepester", \
    "convo/text/blocked", "convo/text/unblocked", "convo/text/blockedmsg", \
    "convo/text/idle", "convo/input/style", "memos/memoicon", \
    "memos/textarea/style", "memos/systemMsgColor", "convo/text/joinmemo", \
    "memos/input/style", "main/menus/rclickchumlist/banuser", \
    "main/menus/rclickchumlist/opuser", "main/menus/rclickchumlist/voiceuser", \
    "memos/margins", "convo/text/openmemo", "memos/size", "memos/style", \
    "memos/label/text", "memos/label/style", "memos/label/align/h", \
    "memos/label/align/v", "memos/label/maxheight", "memos/label/minheight", \
    "memos/userlist/style", "memos/userlist/width", "memos/time/text/width", \
    "memos/time/text/style", "memos/time/arrows/left", \
    "memos/time/arrows/style", "memos/time/buttons/style", \
    "memos/time/arrows/right", "memos/op/icon", "memos/voice/icon", \
    "convo/text/closememo", "convo/text/kickedmemo", \
    "main/chums/userlistcolor", "main/defaultwindow/style", \
    "main/chums/moods", "main/chums/moods/chummy/icon", "main/menus/help/help", \
    "main/menus/help/calsprite", "main/menus/help/nickserv", "main/menus/help/chanserv", \
    "main/menus/rclickchumlist/invitechum", "main/menus/client/randen", \
    "main/menus/rclickchumlist/memosetting", "main/menus/rclickchumlist/memonoquirk", \
    "main/menus/rclickchumlist/memohidden", "main/menus/rclickchumlist/memoinvite", \
    "main/menus/rclickchumlist/memomute", "main/menus/rclickchumlist/notes"]

    for n in needs:
        try:
            theme[n]
        except KeyError:
            raise ThemeException("Missing theme requirement: %s" % (n))
