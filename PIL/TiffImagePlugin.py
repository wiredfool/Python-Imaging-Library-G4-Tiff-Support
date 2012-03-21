#
# The Python Imaging Library.
# $Id$
#
# TIFF file handling
#
# TIFF is a flexible, if somewhat aged, image file format originally
# defined by Aldus.  Although TIFF supports a wide variety of pixel
# layouts and compression methods, the name doesn't really stand for
# "thousands of incompatible file formats," it just feels that way.
#
# To read TIFF data from a stream, the stream must be seekable.  For
# progressive decoding, make sure to use TIFF files where the tag
# directory is placed first in the file.
#
# History:
# 1995-09-01 fl   Created
# 1996-05-04 fl   Handle JPEGTABLES tag
# 1996-05-18 fl   Fixed COLORMAP support
# 1997-01-05 fl   Fixed PREDICTOR support
# 1997-08-27 fl   Added support for rational tags (from Perry Stoll)
# 1998-01-10 fl   Fixed seek/tell (from Jan Blom)
# 1998-07-15 fl   Use private names for internal variables
# 1999-06-13 fl   Rewritten for PIL 1.0 (1.0)
# 2000-10-11 fl   Additional fixes for Python 2.0 (1.1)
# 2001-04-17 fl   Fixed rewind support (seek to frame 0) (1.2)
# 2001-05-12 fl   Added write support for more tags (from Greg Couch) (1.3)
# 2001-12-18 fl   Added workaround for broken Matrox library
# 2002-01-18 fl   Don't mess up if photometric tag is missing (D. Alan Stewart)
# 2003-05-19 fl   Check FILLORDER tag
# 2003-09-26 fl   Added RGBa support
# 2004-02-24 fl   Added DPI support; fixed rational write support
# 2005-02-07 fl   Added workaround for broken Corel Draw 10 files
# 2006-01-09 fl   Added support for float/double tags (from Russell Nelson)
#
# Copyright (c) 1997-2006 by Secret Labs AB.  All rights reserved.
# Copyright (c) 1995-1997 by Fredrik Lundh
#
# See the README file for information on usage and redistribution.
#

__version__ = "1.3.5"

import Image, ImageFile
import ImagePalette

import array, string, sys, os

II = "II" # little-endian (intel-style)
MM = "MM" # big-endian (motorola-style)

try:
    if sys.byteorder == "little":
        native_prefix = II
    else:
        native_prefix = MM
except AttributeError:
    if ord(array.array("i",[1]).tostring()[0]):
        native_prefix = II
    else:
        native_prefix = MM

#
# --------------------------------------------------------------------
# Read TIFF files

def il16(c,o=0):
    return ord(c[o]) + (ord(c[o+1])<<8)
def il32(c,o=0):
    return ord(c[o]) + (ord(c[o+1])<<8) + (ord(c[o+2])<<16) + (ord(c[o+3])<<24)
def ol16(i):
    return chr(i&255) + chr(i>>8&255)
def ol32(i):
    return chr(i&255) + chr(i>>8&255) + chr(i>>16&255) + chr(i>>24&255)

def ib16(c,o=0):
    return ord(c[o+1]) + (ord(c[o])<<8)
def ib32(c,o=0):
    return ord(c[o+3]) + (ord(c[o+2])<<8) + (ord(c[o+1])<<16) + (ord(c[o])<<24)
def ob16(i):
    return chr(i>>8&255) + chr(i&255)
def ob32(i):
    return chr(i>>24&255) + chr(i>>16&255) + chr(i>>8&255) + chr(i&255)

# a few tag names, just to make the code below a bit more readable
IMAGEWIDTH = 256
IMAGELENGTH = 257
BITSPERSAMPLE = 258
COMPRESSION = 259
PHOTOMETRIC_INTERPRETATION = 262
FILLORDER = 266
IMAGEDESCRIPTION = 270
STRIPOFFSETS = 273
SAMPLESPERPIXEL = 277
ROWSPERSTRIP = 278
STRIPBYTECOUNTS = 279
X_RESOLUTION = 282
Y_RESOLUTION = 283
PLANAR_CONFIGURATION = 284
RESOLUTION_UNIT = 296
SOFTWARE = 305
DATE_TIME = 306
ARTIST = 315
PREDICTOR = 317
COLORMAP = 320
TILEOFFSETS = 324
EXTRASAMPLES = 338
SAMPLEFORMAT = 339
JPEGTABLES = 347
COPYRIGHT = 33432
IPTC_NAA_CHUNK = 33723 # newsphoto properties
PHOTOSHOP_CHUNK = 34377 # photoshop properties
ICCPROFILE = 34675
EXIFIFD = 34665
XMP = 700

COMPRESSION_INFO = {
    # Compression => pil compression name
    1: "raw",
    2: "tiff_ccitt",
    3: "group3",
    4: "group4",
    5: "tiff_lzw",
    6: "tiff_jpeg", # obsolete
    7: "jpeg",
    32771: "tiff_raw_16", # 16-bit padding
    32773: "packbits"
}

COMPRESSION_INFO_REV = dict([(v,k) for (k,v) in COMPRESSION_INFO.items()])

OPEN_INFO = {
    # (ByteOrder, PhotoInterpretation, SampleFormat, FillOrder, BitsPerSample,
    #  ExtraSamples) => mode, rawmode
    (II, 0, 1, 1, (1,), ()): ("1", "1;I"),
    (II, 0, 1, 2, (1,), ()): ("1", "1;IR"),
    (II, 0, 1, 1, (8,), ()): ("L", "L;I"),
    (II, 0, 1, 2, (8,), ()): ("L", "L;IR"),
    (II, 1, 1, 1, (1,), ()): ("1", "1"),
    (II, 1, 1, 2, (1,), ()): ("1", "1;R"),
    (II, 1, 1, 1, (8,), ()): ("L", "L"),
    (II, 1, 1, 1, (8,8), (2,)): ("LA", "LA"),
    (II, 1, 1, 2, (8,), ()): ("L", "L;R"),
    (II, 1, 1, 1, (16,), ()): ("I;16", "I;16"),
    (II, 1, 2, 1, (16,), ()): ("I;16S", "I;16S"),
    (II, 1, 2, 1, (32,), ()): ("I", "I;32S"),
    (II, 1, 3, 1, (32,), ()): ("F", "F;32F"),
    (II, 2, 1, 1, (8,8,8), ()): ("RGB", "RGB"),
    (II, 2, 1, 2, (8,8,8), ()): ("RGB", "RGB;R"),
    (II, 2, 1, 1, (8,8,8,8), (0,)): ("RGBX", "RGBX"),
    (II, 2, 1, 1, (8,8,8,8), (1,)): ("RGBA", "RGBa"),
    (II, 2, 1, 1, (8,8,8,8), (2,)): ("RGBA", "RGBA"),
    (II, 2, 1, 1, (8,8,8,8), (999,)): ("RGBA", "RGBA"), # corel draw 10
    (II, 3, 1, 1, (1,), ()): ("P", "P;1"),
    (II, 3, 1, 2, (1,), ()): ("P", "P;1R"),
    (II, 3, 1, 1, (2,), ()): ("P", "P;2"),
    (II, 3, 1, 2, (2,), ()): ("P", "P;2R"),
    (II, 3, 1, 1, (4,), ()): ("P", "P;4"),
    (II, 3, 1, 2, (4,), ()): ("P", "P;4R"),
    (II, 3, 1, 1, (8,), ()): ("P", "P"),
    (II, 3, 1, 1, (8,8), (2,)): ("PA", "PA"),
    (II, 3, 1, 2, (8,), ()): ("P", "P;R"),
    (II, 5, 1, 1, (8,8,8,8), ()): ("CMYK", "CMYK"),
    (II, 6, 1, 1, (8,8,8), ()): ("YCbCr", "YCbCr"),
    (II, 8, 1, 1, (8,8,8), ()): ("LAB", "LAB"),

    (MM, 0, 1, 1, (1,), ()): ("1", "1;I"),
    (MM, 0, 1, 2, (1,), ()): ("1", "1;IR"),
    (MM, 0, 1, 1, (8,), ()): ("L", "L;I"),
    (MM, 0, 1, 2, (8,), ()): ("L", "L;IR"),
    (MM, 1, 1, 1, (1,), ()): ("1", "1"),
    (MM, 1, 1, 2, (1,), ()): ("1", "1;R"),
    (MM, 1, 1, 1, (8,), ()): ("L", "L"),
    (MM, 1, 1, 1, (8,8), (2,)): ("LA", "LA"),
    (MM, 1, 1, 2, (8,), ()): ("L", "L;R"),
    (MM, 1, 1, 1, (16,), ()): ("I;16B", "I;16B"),
    (MM, 1, 2, 1, (16,), ()): ("I;16BS", "I;16BS"),
    (MM, 1, 2, 1, (32,), ()): ("I;32BS", "I;32BS"),
    (MM, 1, 3, 1, (32,), ()): ("F;32BF", "F;32BF"),
    (MM, 2, 1, 1, (8,8,8), ()): ("RGB", "RGB"),
    (MM, 2, 1, 2, (8,8,8), ()): ("RGB", "RGB;R"),
    (MM, 2, 1, 1, (8,8,8,8), (0,)): ("RGBX", "RGBX"),
    (MM, 2, 1, 1, (8,8,8,8), (1,)): ("RGBA", "RGBa"),
    (MM, 2, 1, 1, (8,8,8,8), (2,)): ("RGBA", "RGBA"),
    (MM, 2, 1, 1, (8,8,8,8), (999,)): ("RGBA", "RGBA"), # corel draw 10
    (MM, 3, 1, 1, (1,), ()): ("P", "P;1"),
    (MM, 3, 1, 2, (1,), ()): ("P", "P;1R"),
    (MM, 3, 1, 1, (2,), ()): ("P", "P;2"),
    (MM, 3, 1, 2, (2,), ()): ("P", "P;2R"),
    (MM, 3, 1, 1, (4,), ()): ("P", "P;4"),
    (MM, 3, 1, 2, (4,), ()): ("P", "P;4R"),
    (MM, 3, 1, 1, (8,), ()): ("P", "P"),
    (MM, 3, 1, 1, (8,8), (2,)): ("PA", "PA"),
    (MM, 3, 1, 2, (8,), ()): ("P", "P;R"),
    (MM, 5, 1, 1, (8,8,8,8), ()): ("CMYK", "CMYK"),
    (MM, 6, 1, 1, (8,8,8), ()): ("YCbCr", "YCbCr"),
    (MM, 8, 1, 1, (8,8,8), ()): ("LAB", "LAB"),

}

PREFIXES = ["MM\000\052", "II\052\000", "II\xBC\000"]

def _accept(prefix):
    return prefix[:4] in PREFIXES

##
# Wrapper for TIFF IFDs.

class ImageFileDirectory:

    # represents a TIFF tag directory.  to speed things up,
    # we don't decode tags unless they're asked for.

    def __init__(self, prefix):
        self.prefix = prefix[:2]
        if self.prefix == MM:
            self.i16, self.i32 = ib16, ib32
            self.o16, self.o32 = ob16, ob32
        elif self.prefix == II:
            self.i16, self.i32 = il16, il32
            self.o16, self.o32 = ol16, ol32
        else:
            raise SyntaxError("not a TIFF IFD")
        self.reset()

    def reset(self):
        self.tags = {}
        self.tagdata = {}
        self.tagtype = {} # added 2008-06-05 by Florian Hoech
        self.next = None

    # dictionary API (sort of)

    def keys(self):
        return self.tagdata.keys() + self.tags.keys()

    def items(self):
        items = self.tags.items()
        for tag in self.tagdata.keys():
            items.append((tag, self[tag]))
        return items

    def __len__(self):
        return len(self.tagdata) + len(self.tags)

    def __getitem__(self, tag):
        try:
            return self.tags[tag]
        except KeyError:
            type, data = self.tagdata[tag] # unpack on the fly
            size, handler = self.load_dispatch[type]
            self.tags[tag] = data = handler(self, data)
            del self.tagdata[tag]
            return data

    def get(self, tag, default=None):
        try:
            return self[tag]
        except KeyError:
            return default

    def getscalar(self, tag, default=None):
        try:
            value = self[tag]
            if len(value) != 1:
                if tag == SAMPLEFORMAT:
                    # work around broken (?) matrox library
                    # (from Ted Wright, via Bob Klimek)
                    raise KeyError # use default
                raise ValueError, "not a scalar"
            return value[0]
        except KeyError:
            if default is None:
                raise
            return default

    def has_key(self, tag):
        return self.tags.has_key(tag) or self.tagdata.has_key(tag)

    def __setitem__(self, tag, value):
        if type(value) is not type(()):
            value = (value,)
        self.tags[tag] = value

    # load primitives

    load_dispatch = {}

    def load_byte(self, data):
        l = []
        for i in range(len(data)):
            l.append(ord(data[i]))
        return tuple(l)
    load_dispatch[1] = (1, load_byte)

    def load_string(self, data):
        if data[-1:] == '\0':
            data = data[:-1]
        return data
    load_dispatch[2] = (1, load_string)

    def load_short(self, data):
        l = []
        for i in range(0, len(data), 2):
            l.append(self.i16(data, i))
        return tuple(l)
    load_dispatch[3] = (2, load_short)

    def load_long(self, data):
        l = []
        for i in range(0, len(data), 4):
            l.append(self.i32(data, i))
        return tuple(l)
    load_dispatch[4] = (4, load_long)

    def load_rational(self, data):
        l = []
        for i in range(0, len(data), 8):
            l.append((self.i32(data, i), self.i32(data, i+4)))
        return tuple(l)
    load_dispatch[5] = (8, load_rational)

    def load_float(self, data):
        a = array.array("f", data)
        if self.prefix != native_prefix:
            a.byteswap()
        return tuple(a)
    load_dispatch[11] = (4, load_float)

    def load_double(self, data):
        a = array.array("d", data)
        if self.prefix != native_prefix:
            a.byteswap()
        return tuple(a)
    load_dispatch[12] = (8, load_double)

    def load_undefined(self, data):
        # Untyped data
        return data
    load_dispatch[7] = (1, load_undefined)

    def load(self, fp):
        # load tag dictionary

        self.reset()

        i16 = self.i16
        i32 = self.i32

        for i in range(i16(fp.read(2))):

            ifd = fp.read(12)

            tag, typ = i16(ifd), i16(ifd, 2)

            if Image.DEBUG:
                import TiffTags
                tagname = TiffTags.TAGS.get(tag, "unknown")
                typname = TiffTags.TYPES.get(typ, "unknown")
                print "tag: %s (%d)" % (tagname, tag),
                print "- type: %s (%d)" % (typname, typ),

            try:
                dispatch = self.load_dispatch[typ]
            except KeyError:
                if Image.DEBUG:
                    print "- unsupported type", typ
                continue # ignore unsupported type

            size, handler = dispatch

            size = size * i32(ifd, 4)

            # Get and expand tag value
            if size > 4:
                here = fp.tell()
                fp.seek(i32(ifd, 8))
                data = ImageFile._safe_read(fp, size)
                fp.seek(here)
            else:
                data = ifd[8:8+size]

            if len(data) != size:
                raise IOError, "not enough data"

            self.tagdata[tag] = typ, data
            self.tagtype[tag] = typ

            if Image.DEBUG:
                if tag in (COLORMAP, IPTC_NAA_CHUNK, PHOTOSHOP_CHUNK, ICCPROFILE, XMP):
                    print "- value: <table: %d bytes>" % size
                else:
                    print "- value:", self[tag]

        self.next = i32(fp.read(4))

    # save primitives

    def save(self, fp):

        o16 = self.o16
        o32 = self.o32

        fp.write(o16(len(self.tags)))

        # always write in ascending tag order
        tags = self.tags.items()
        tags.sort()

        directory = []
        append = directory.append

        offset = fp.tell() + len(self.tags) * 12 + 4

        stripoffsets = None

        # pass 1: convert tags to binary format
        for tag, value in tags:

            typ = None

            if self.tagtype.has_key(tag):
                typ = self.tagtype[tag]

            if typ == 1:
                # byte data
                data = value = string.join(map(chr, value), "")
            elif typ == 7:
                # untyped data
                data = value = string.join(value, "")
            elif type(value[0]) is type(""):
                # string data
                typ = 2
                data = value = string.join(value, "\0") + "\0"
            else:
                # integer data
                if tag == STRIPOFFSETS:
                    stripoffsets = len(directory)
                    typ = 4 # to avoid catch-22
                elif tag in (X_RESOLUTION, Y_RESOLUTION):
                    # identify rational data fields
                    typ = 5
                elif not typ:
                    typ = 3
                    for v in value:
                        if v >= 65536:
                            typ = 4
                if typ == 3:
                    data = string.join(map(o16, value), "")
                else:
                    data = string.join(map(o32, value), "")

            if Image.DEBUG:
                import TiffTags
                tagname = TiffTags.TAGS.get(tag, "unknown")
                typname = TiffTags.TYPES.get(typ, "unknown")
                print "save: %s (%d)" % (tagname, tag),
                print "- type: %s (%d)" % (typname, typ),
                if tag in (COLORMAP, IPTC_NAA_CHUNK, PHOTOSHOP_CHUNK, ICCPROFILE, XMP):
                    size = len(data)
                    print "- value: <table: %d bytes>" % size
                else:
                    print "- value:", value

            # figure out if data fits into the directory
            if len(data) == 4:
                append((tag, typ, len(value), data, ""))
            elif len(data) < 4:
                append((tag, typ, len(value), data + (4-len(data))*"\0", ""))
            else:
                count = len(value)
                if typ == 5:
                    count = count / 2        # adjust for rational data field
                append((tag, typ, count, o32(offset), data))
                offset = offset + len(data)
                if offset & 1:
                    offset = offset + 1 # word padding

        # update strip offset data to point beyond auxiliary data
        if stripoffsets is not None:
            tag, typ, count, value, data = directory[stripoffsets]
            assert not data, "multistrip support not yet implemented"
            value = o32(self.i32(value) + offset)
            directory[stripoffsets] = tag, typ, count, value, data

        # pass 2: write directory to file
        for tag, typ, count, value, data in directory:
            if Image.DEBUG > 1:
                print tag, typ, count, repr(value), repr(data)
            fp.write(o16(tag) + o16(typ) + o32(count) + value)

        # -- overwrite here for multi-page --
        fp.write("\0\0\0\0") # end of directory

        # pass 3: write auxiliary data to file
        for tag, typ, count, value, data in directory:
            fp.write(data)
            if len(data) & 1:
                fp.write("\0")

        return offset

##
# Image plugin for TIFF files.

class TiffImageFile(ImageFile.ImageFile):

    format = "TIFF"
    format_description = "Adobe TIFF"

    def _open(self):
        "Open the first image in a TIFF file"

        # Header
        ifh = self.fp.read(8)

        if ifh[:4] not in PREFIXES:
            raise SyntaxError, "not a TIFF file"

        # image file directory (tag dictionary)
        self.tag = self.ifd = ImageFileDirectory(ifh[:2])

        # setup frame pointers
        self.__first = self.__next = self.ifd.i32(ifh, 4)
        self.__frame = -1
        self.__fp = self.fp

        if Image.DEBUG:
            print "*** TiffImageFile._open ***"
            print "- __first:", self.__first
            print "- ifh: ", ifh

       # and load the first frame
        self._seek(0)

    def seek(self, frame):
        "Select a given frame as current image"

        if frame < 0:
            frame = 0
        self._seek(frame)

    def tell(self):
        "Return the current frame number"

        return self._tell()

    def _seek(self, frame):

        self.fp = self.__fp
        if frame < self.__frame:
            # rewind file
            self.__frame = -1
            self.__next = self.__first
        while self.__frame < frame:
            if not self.__next:
                raise EOFError, "no more images in TIFF file"
            self.fp.seek(self.__next)
            self.tag.load(self.fp)
            self.__next = self.tag.next
            self.__frame = self.__frame + 1
        self._setup()

    def _tell(self):

        return self.__frame

    def _decoder(self, rawmode, layer, tile=None):
        "Setup decoder contexts"

        args = None
        if rawmode == "RGB" and self._planar_configuration == 2:
            rawmode = rawmode[layer]
        compression = self._compression
        if compression == "raw":
            args = (rawmode, 0, 1)
        elif compression == "jpeg":
            args = rawmode, ""
            if self.tag.has_key(JPEGTABLES):
                # Hack to handle abbreviated JPEG headers
                self.tile_prefix = self.tag[JPEGTABLES]
        elif compression == "packbits":
            args = rawmode
        elif compression == "tiff_lzw":
            args = rawmode
            if self.tag.has_key(317):
                # Section 14: Differencing Predictor
                self.decoderconfig = (self.tag[PREDICTOR][0],)
                
        if self.tag.has_key(ICCPROFILE):
            self.info['icc_profile'] = self.tag[ICCPROFILE]

        return args

    def _load_libtiff(self):
        """ Overload method triggered when we detect a g3/g4 tiff
            Calls out to lib tiff """

        pixel = Image.Image.load(self)

        if self.tile is None:
            raise IOError("cannot load this image")
        if not self.tile:
            return pixel

        self.load_prepare()


        
        if not len(self.tile) == 1:
            raise IOError("Not exactly one tile")


        d, e, o, a = self.tile[0]
        d = Image._getdecoder(self.mode, d, a, self.decoderconfig)
        try:
            d.setimage(self.im, e)
        except ValueError:
            raise IOError("Couldn't set the image")

        if hasattr(self.fp, "fileno"):
            # we've got a actual file on disk, pass in the fp.
            if Image.DEBUG:
                print "have fileno, calling fileno version of the decoder."
            self.fp.seek(0)
            n,e = d.decode("fpfp") # 4 bytes, otherwise the trace might error out
        elif hasattr(self.fp, "getvalue"):
            # We've got a stringio like thing passed in. Yay for all in memory.
            # The decoder needs the entire file in one shot, so there's not
            # a lot we can do here other than give it the entire file.
            # unless we could do something like get the address of the underlying
            # string for stringio.
            if Image.DEBUG:
                print "have getvalue. just sending in a string from getvalue"
            n,e = d.decode(self.fp.getvalue())
        else:
            # we have something else.
            if Image.DEBUG:
                print "don't have fileno or getvalue. just reading"
            # UNDONE -- so much for that buffer size thing. 
            n, e = d.decode(self.fp.read())

        
        self.tile = []
        self.readonly = 0
        self.fp = None # might be shared

        if e < 0:
            raise_ioerror(e)

        self.load_end()

        return Image.Image.load(self)

        
            
    def _setup(self):
        "Setup this image object based on current tags"

        if self.tag.has_key(0xBC01):
            raise IOError, "Windows Media Photo files not yet supported"

        getscalar = self.tag.getscalar

        # extract relevant tags
        self._compression = COMPRESSION_INFO[getscalar(COMPRESSION, 1)]
        self._planar_configuration = getscalar(PLANAR_CONFIGURATION, 1)

        # photometric is a required tag, but not everyone is reading
        # the specification
        photo = getscalar(PHOTOMETRIC_INTERPRETATION, 0)

        fillorder = getscalar(FILLORDER, 1)

        if Image.DEBUG:
            print "*** Summary ***"
            print "- compression:", self._compression
            print "- photometric_interpretation:", photo
            print "- planar_configuration:", self._planar_configuration
            print "- fill_order:", fillorder

        # size
        xsize = getscalar(IMAGEWIDTH)
        ysize = getscalar(IMAGELENGTH)
        self.size = xsize, ysize

        if Image.DEBUG:
            print "- size:", self.size

        format = getscalar(SAMPLEFORMAT, 1)

        # mode: check photometric interpretation and bits per pixel
        key = (
            self.tag.prefix, photo, format, fillorder,
            self.tag.get(BITSPERSAMPLE, (1,)),
            self.tag.get(EXTRASAMPLES, ())
            )
        if Image.DEBUG:
            print "format key:", key
        try:
            self.mode, rawmode = OPEN_INFO[key]
        except KeyError:
            if Image.DEBUG:
                print "- unsupported format"
            raise SyntaxError, "unknown pixel mode"

        if Image.DEBUG:
            print "- raw mode:", rawmode
            print "- pil mode:", self.mode

        self.info["compression"] = self._compression

        xres = getscalar(X_RESOLUTION, (1, 1))
        yres = getscalar(Y_RESOLUTION, (1, 1))

        if xres and yres:
            xres = xres[0] / (xres[1] or 1)
            yres = yres[0] / (yres[1] or 1)
            resunit = getscalar(RESOLUTION_UNIT, 1)
            if resunit == 2: # dots per inch
                self.info["dpi"] = xres, yres
            elif resunit == 3: # dots per centimeter. convert to dpi
                self.info["dpi"] = xres * 2.54, yres * 2.54
            else: # No absolute unit of measurement
                self.info["resolution"] = xres, yres

        # build tile descriptors
        x = y = l = 0
        self.tile = []
        if self.tag.has_key(STRIPOFFSETS):
            # striped image
            offsets = self.tag[STRIPOFFSETS]
            h = getscalar(ROWSPERSTRIP, ysize)
            w = self.size[0]
            if self._compression in ["tiff_ccitt", "group3",
                                     "group4", "tiff_raw_16"]:
                if Image.DEBUG:
                    print "Activating g4 compression for whole file"

                # Decoder expects entire file as one tile.
                # There's a buffer size limit in load (64k)
                # so large g4 images will fail if we use that
                # function. 
                #
                # Setup the one tile for the whole image, then
                # replace the existing load function with our
                # _load_libtiff function.
                
                self.load = self._load_libtiff
                
                # To be nice on memory footprint, if there's a
                # file descriptor, use that instead of reading
                # into a string in python.

                # libtiff closes the file descriptor, so pass in a dup. 
                fp = hasattr(self.fp, "fileno") and os.dup(self.fp.fileno())

                # Offset in the tile tuple is 0, we go from 0,0 to
                # w,h, and we only do this once -- eds
                a = (rawmode, self._compression, fp )
                self.tile.append(
                    (self._compression,
                     (0, 0, w, ysize),
                     0, a))
                a = None

            else:
                for i in range(len(offsets)):
                    a = self._decoder(rawmode, l, i)
                    self.tile.append(
                        (self._compression,
                        (0, min(y, ysize), w, min(y+h, ysize)),
                        offsets[i], a))
                    print "tiles: %s" % self.tile
                    y = y + h
                    if y >= self.size[1]:
                        x = y = 0
                        l = l + 1
                    a = None
        elif self.tag.has_key(TILEOFFSETS):
            # tiled image
            w = getscalar(322)
            h = getscalar(323)
            a = None
            for o in self.tag[TILEOFFSETS]:
                if not a:
                    a = self._decoder(rawmode, l)
                # FIXME: this doesn't work if the image size
                # is not a multiple of the tile size...
                self.tile.append(
                    (self._compression,
                    (x, y, x+w, y+h),
                    o, a))
                x = x + w
                if x >= self.size[0]:
                    x, y = 0, y + h
                    if y >= self.size[1]:
                        x = y = 0
                        l = l + 1
                        a = None
        else:
            if Image.DEBUG:
                print "- unsupported data organization"
            raise SyntaxError("unknown data organization")

        # fixup palette descriptor

        if self.mode == "P":
            palette = map(lambda a: chr(a / 256), self.tag[COLORMAP])
            self.palette = ImagePalette.raw("RGB;L", string.join(palette, ""))
#
# --------------------------------------------------------------------
# Write TIFF files

# little endian is default except for image modes with explict big endian byte-order

SAVE_INFO = {
    # mode => rawmode, byteorder, photometrics, sampleformat, bitspersample, extra
    "1": ("1", II, 1, 1, (1,), None),
    "L": ("L", II, 1, 1, (8,), None),
    "LA": ("LA", II, 1, 1, (8,8), 2),
    "P": ("P", II, 3, 1, (8,), None),
    "PA": ("PA", II, 3, 1, (8,8), 2),
    "I": ("I;32S", II, 1, 2, (32,), None),
    "I;16": ("I;16", II, 1, 1, (16,), None),
    "I;16S": ("I;16S", II, 1, 2, (16,), None),
    "F": ("F;32F", II, 1, 3, (32,), None),
    "RGB": ("RGB", II, 2, 1, (8,8,8), None),
    "RGBX": ("RGBX", II, 2, 1, (8,8,8,8), 0),
    "RGBA": ("RGBA", II, 2, 1, (8,8,8,8), 2),
    "CMYK": ("CMYK", II, 5, 1, (8,8,8,8), None),
    "YCbCr": ("YCbCr", II, 6, 1, (8,8,8), None),
    "LAB": ("LAB", II, 8, 1, (8,8,8), None),

    "I;32BS": ("I;32BS", MM, 1, 2, (32,), None),
    "I;16B": ("I;16B", MM, 1, 1, (16,), None),
    "I;16BS": ("I;16BS", MM, 1, 2, (16,), None),
    "F;32BF": ("F;32BF", MM, 1, 3, (32,), None),
}

def _cvt_res(value):
    # convert value to TIFF rational number -- (numerator, denominator)
    if type(value) in (type([]), type(())):
        assert(len(value) % 2 == 0)
        return value
    if type(value) == type(1):
        return (value, 1)
    value = float(value)
    return (int(value * 65536), 65536)

def _save(im, fp, filename):

    try:
        rawmode, prefix, photo, format, bits, extra = SAVE_INFO[im.mode]
    except KeyError:
        raise IOError, "cannot write mode %s as TIFF" % im.mode

    ifd = ImageFileDirectory(prefix)

    compression = im.info.get('compression','raw')
    libtiff = compression in ["tiff_ccitt", "group3",
                              "group4", "tiff_raw_16"]

    # -- multi-page -- skip TIFF header on subsequent pages
    if not libtiff and fp.tell() == 0:
        # tiff header (write via IFD to get everything right)
        # PIL always starts the first IFD at offset 8
        fp.write(ifd.prefix + ifd.o16(42) + ifd.o32(8))

    ifd[IMAGEWIDTH] = im.size[0]
    ifd[IMAGELENGTH] = im.size[1]

    # additions written by Greg Couch, gregc@cgl.ucsf.edu
    # inspired by image-sig posting from Kevin Cazabon, kcazabon@home.com
    if hasattr(im, 'tag'):
        # preserve tags from original TIFF image file
        for key in (RESOLUTION_UNIT, X_RESOLUTION, Y_RESOLUTION):
            if im.tag.tagdata.has_key(key):
                ifd[key] = im.tag.tagdata.get(key)
        # preserve some more tags from original TIFF image file
        # -- 2008-06-06 Florian Hoech
        ifd.tagtype = im.tag.tagtype
        for key in (IPTC_NAA_CHUNK, PHOTOSHOP_CHUNK, XMP):
            if im.tag.has_key(key):
                ifd[key] = im.tag[key]
        # preserve ICC profile (should also work when saving other formats
        # which support profiles as TIFF) -- 2008-06-06 Florian Hoech
        if im.info.has_key("icc_profile"):
            ifd[ICCPROFILE] = im.info["icc_profile"]
    if im.encoderinfo.has_key("description"):
        ifd[IMAGEDESCRIPTION] = im.encoderinfo["description"]
    if im.encoderinfo.has_key("resolution"):
        ifd[X_RESOLUTION] = ifd[Y_RESOLUTION] \
                                = _cvt_res(im.encoderinfo["resolution"])
    if im.encoderinfo.has_key("x resolution"):
        ifd[X_RESOLUTION] = _cvt_res(im.encoderinfo["x resolution"])
    if im.encoderinfo.has_key("y resolution"):
        ifd[Y_RESOLUTION] = _cvt_res(im.encoderinfo["y resolution"])
    if im.encoderinfo.has_key("resolution unit"):
        unit = im.encoderinfo["resolution unit"]
        if unit == "inch":
            ifd[RESOLUTION_UNIT] = 2
        elif unit == "cm" or unit == "centimeter":
            ifd[RESOLUTION_UNIT] = 3
        else:
            ifd[RESOLUTION_UNIT] = 1
    if im.encoderinfo.has_key("software"):
        ifd[SOFTWARE] = im.encoderinfo["software"]
    if im.encoderinfo.has_key("date time"):
        ifd[DATE_TIME] = im.encoderinfo["date time"]
    if im.encoderinfo.has_key("artist"):
        ifd[ARTIST] = im.encoderinfo["artist"]
    if im.encoderinfo.has_key("copyright"):
        ifd[COPYRIGHT] = im.encoderinfo["copyright"]

    dpi = im.encoderinfo.get("dpi")
    if dpi:
        ifd[RESOLUTION_UNIT] = 2
        ifd[X_RESOLUTION] = _cvt_res(dpi[0])
        ifd[Y_RESOLUTION] = _cvt_res(dpi[1])

    if bits != (1,):
        ifd[BITSPERSAMPLE] = bits
        if len(bits) != 1:
            ifd[SAMPLESPERPIXEL] = len(bits)
    if extra is not None:
        ifd[EXTRASAMPLES] = extra
    if format != 1:
        ifd[SAMPLEFORMAT] = format

    ifd[PHOTOMETRIC_INTERPRETATION] = photo

    if im.mode == "P":
        lut = im.im.getpalette("RGB", "RGB;L")
        ifd[COLORMAP] = tuple(map(lambda v: ord(v) * 256, lut))

    # data orientation
    stride = len(bits) * ((im.size[0]*bits[0]+7)/8)
    ifd[ROWSPERSTRIP] = im.size[1]
    ifd[STRIPBYTECOUNTS] = stride * im.size[1]
    ifd[STRIPOFFSETS] = 0 # this is adjusted by IFD writer
    ifd[COMPRESSION] = COMPRESSION_INFO_REV.get(compression,1) # no compression by default

    if libtiff:
        if Image.DEBUG:
            print "Saving using libtiff encoder"
            print ifd.items()
        _fp = 0
        if hasattr(fp, "fileno"):
            fp.seek(0)
            _fp = os.dup(fp.fileno())

        blocklist =  [STRIPOFFSETS, STRIPBYTECOUNTS, ROWSPERSTRIP, ICCPROFILE] # ICC Profile crashes.
        atts = dict([(k,v) for (k,(v,)) in ifd.items() if k not in blocklist])
        try:
            # pull in more bits from the original file, e.g x,y resolution
            # so that we can save(load('')) == original file.
            for k,v in im.ifd.items():
                if k not in atts and k not in blocklist:
                    if type(v[0]) == tuple and len(v) > 1:
                       # A tuple of more than one rational tuples
                        # flatten to floats, following tiffcp.c->cpTag->TIFF_RATIONAL
                        atts[k] = [float(elt[0])/float(elt[1]) for elt in v]
                        continue
                    if type(v[0]) == tuple and len(v) == 1:
                       # A tuple of one rational tuples
                        # flatten to floats, following tiffcp.c->cpTag->TIFF_RATIONAL
                        atts[k] = float(v[0][0])/float(v[0][1])
                        continue
                    if type(v) == tuple and len(v) == 1:
                        # int or similar
                        atts[k] = v[0]
                        continue
                    if type(v) == str:
                        atts[k] = v
                        continue
                    
        except:
            # if we don't have an ifd here, just punt.
            pass
        if Image.DEBUG:
            print atts
        a = (rawmode, compression, _fp, filename, atts)
        e = Image._getencoder(im.mode, compression, a, im.encoderconfig)
        e.setimage(im.im, (0,0)+im.size)
        while 1:
            l, s, d = e.encode(16*1024) # undone, change to self.decodermaxblock
            if not _fp:
                fp.write(d)
            if s:
                break
        if s < 0:
            raise IOError("encoder error %d when writing image file" % s)
        
    else:
        offset = ifd.save(fp)

        ImageFile._save(im, fp, [
            ("raw", (0,0)+im.size, offset, (rawmode, stride, 1))
            ])


    # -- helper for multi-page save --
    if im.encoderinfo.has_key("_debug_multipage"):
        #just to access o32 and o16 (using correct byte order)
        im._debug_multipage = ifd

#
# --------------------------------------------------------------------
# Register

Image.register_open("TIFF", TiffImageFile, _accept)
Image.register_save("TIFF", _save)

Image.register_extension("TIFF", ".tif")
Image.register_extension("TIFF", ".tiff")

Image.register_mime("TIFF", "image/tiff")
